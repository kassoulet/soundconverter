"""lameinfomux - GStreamer element writing a LAME "Info" frame into CBR MP3 streams.

The first frame of the stream is a silent frame holding the frame count, the
byte count and the encoder delay/padding, which gapless players need.
Like xingmux, a placeholder frame is written first and rewritten at EOS with
the final values, so the downstream sink must be seekable (filesink is).
"""

from typing import NamedTuple

import gi

gi.require_version("Gst", "1.0")

from gi.repository import GObject, Gst  # noqa: E402 (gi.require_version first)

# lame always delays the encoded audio by 576 samples
ENCODER_DELAY = 576
# delay and padding are stored as 12 bit values
MAX_12BIT = 0xFFF
# size of the Xing/Info tag, starting at "Info" and ending with the tag CRC
TAG_SIZE = 156

# MPEG layer III bitrates in kbps, indexed by the header bitrate field
BITRATES = {
    True: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    False: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
}
# sample rates indexed by the header MPEG version (3: MPEG-1, 2: MPEG-2, 0: 2.5)
SAMPLE_RATES = {
    3: (44100, 48000, 32000),
    2: (22050, 24000, 16000),
    0: (11025, 12000, 8000),
}


class Frame(NamedTuple):
    """What is needed from an MPEG layer III frame header."""

    size: int
    mpeg1: bool
    mono: bool
    bitrate: int
    rate: int
    samples: int


def parse_frame(data):
    """Parse the 4 byte MPEG layer III frame header at the start of data.

    Returns None if data doesn't start with a supported frame.
    """
    if len(data) < 4:
        return None
    header = int.from_bytes(data[:4], "big")
    version = (header >> 19) & 3
    bitrate_index = (header >> 12) & 0xF
    rate_index = (header >> 10) & 3
    is_layer3 = (header >> 17) & 3 == 1
    if (
        header >> 21 != 0x7FF
        or version == 1
        or not is_layer3
        or bitrate_index in (0, 15)  # free format and invalid
        or rate_index == 3
    ):
        return None
    mpeg1 = version == 3
    bitrate = BITRATES[mpeg1][bitrate_index]
    rate = SAMPLE_RATES[version][rate_index]
    padding = (header >> 9) & 1
    size = (144 if mpeg1 else 72) * bitrate * 1000 // rate + padding
    return Frame(
        size, mpeg1, (header >> 6) & 3 == 3, bitrate, rate, 1152 if mpeg1 else 576
    )


def count_frames(data):
    """Count the consecutive frames at the start of data."""
    count = pos = 0
    while frame := parse_frame(data[pos:]):
        count += 1
        pos += frame.size
    return count


def crc16(data):
    """CRC-16 with polynomial 0x8005 (reflected), as used by the LAME tag."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def build_info_frame(first_header, frames, total_bytes, padding):
    """Build a complete silent MPEG frame holding the Info tag.

    first_header is the header of the first audio frame, which gives the
    version, sample rate and channel mode. frames counts the audio frames
    (not this one) and total_bytes the whole stream including this frame.
    """
    frame = parse_frame(first_header)
    side_info = (17 if frame.mono else 32) if frame.mpeg1 else (9 if frame.mono else 17)
    tag_offset = 4 + side_info

    # The frame must be big enough for the tag, which low bitrates are not.
    # Take the next bitrate that fits, the frame doesn't have to match the stream.
    bitrates = BITRATES[frame.mpeg1]
    bitrate_index = bitrates.index(frame.bitrate)
    while (144 if frame.mpeg1 else 72) * bitrates[
        bitrate_index
    ] * 1000 // frame.rate < tag_offset + TAG_SIZE:
        bitrate_index += 1
    size = (144 if frame.mpeg1 else 72) * bitrates[bitrate_index] * 1000 // frame.rate

    out = bytearray(size)
    out[:4] = first_header
    out[1] |= 1  # no CRC in the frame header
    out[2] = (out[2] & 0x0D) | (bitrate_index << 4)  # keep sample rate, no padding

    tag = tag_offset
    out[tag : tag + 4] = b"Info"  # "Xing" is for VBR
    out[tag + 4 : tag + 8] = (0xF).to_bytes(
        4, "big"
    )  # flags: frames, bytes, toc, scale
    out[tag + 8 : tag + 12] = frames.to_bytes(4, "big")
    out[tag + 12 : tag + 16] = total_bytes.to_bytes(4, "big")
    # 100 bytes toc and 4 bytes quality stay 0 for CBR
    out[tag + 120 : tag + 129] = b"LAME3.100"
    out[tag + 129] = 1  # tag revision 0, CBR
    out[tag + 140] = min(frame.bitrate, 255)  # specified bitrate
    out[tag + 141 : tag + 144] = ((ENCODER_DELAY << 12) | padding).to_bytes(3, "big")
    out[tag + 148 : tag + 152] = total_bytes.to_bytes(4, "big")  # music length
    # music CRC (tag + 152) stays 0, players don't check it
    out[tag + 154 : tag + 156] = crc16(out[: tag + 154]).to_bytes(2, "big")
    return bytes(out)


MP3_CAPS = Gst.Caps.from_string("audio/mpeg, mpegversion=(int)1, layer=(int)3")


class LameInfoMux(Gst.Element):
    """Prepends a LAME Info frame to a CBR MP3 stream."""

    __gstmetadata__ = (
        "LAME Info Mux",
        "Codec/Muxer/Audio",
        "Writes a LAME Info frame at the start of a CBR MP3 stream for gapless playback",
        "SoundConverter",
    )
    __gsttemplates__ = (
        Gst.PadTemplate.new(
            "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS, MP3_CAPS
        ),
        Gst.PadTemplate.new(
            "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS, MP3_CAPS
        ),
    )

    # ponytail: single use, an element can't be restarted after EOS
    def __init__(self):
        super().__init__()
        self.sinkpad = Gst.Pad.new_from_template(self.get_pad_template("sink"), "sink")
        self.sinkpad.set_chain_function_full(self.chain, None)
        self.sinkpad.set_event_function_full(self.sink_event, None)
        self.add_pad(self.sinkpad)
        self.srcpad = Gst.Pad.new_from_template(self.get_pad_template("src"), "src")
        self.add_pad(self.srcpad)

        self.frame = None  # first audio frame
        self.header = None  # its 4 header bytes
        self.info_size = 0
        self.frames = 0
        self.position = 0  # in the output stream, in bytes

    def push_byte_segment(self):
        """Tell downstream that the following buffers start at byte 0."""
        segment = Gst.Segment()
        segment.init(Gst.Format.BYTES)
        return self.srcpad.push_event(Gst.Event.new_segment(segment))

    def push_info_frame(self, padding=0):
        """Push the Info frame at the start of the stream."""
        data = build_info_frame(self.header, self.frames, self.position, padding)
        return self.srcpad.push(Gst.Buffer.new_wrapped(data))

    def chain(self, pad, parent, buffer):
        data = buffer.extract_dup(0, buffer.get_size())

        if self.frame is None:
            self.frame = parse_frame(data)
            if self.frame is None:
                return Gst.FlowReturn.ERROR
            self.header = data[:4]
            self.info_size = len(build_info_frame(self.header, 0, 0, 0))
            self.push_byte_segment()
            # the final values are written when the stream ends
            self.position = self.info_size
            ret = self.push_info_frame()
            if ret != Gst.FlowReturn.OK:
                return ret

        self.frames += count_frames(data)
        self.position += len(data)
        return self.srcpad.push(buffer)

    def sink_event(self, pad, parent, event):
        if event.type == Gst.EventType.SEGMENT:
            return True  # a byte segment is sent with the first buffer instead
        if event.type == Gst.EventType.EOS and self.frame is not None:
            # the buffer timestamps count whole frames, the source knows the real length
            # ponytail: no padding if the source can't tell its position
            ok, position = self.sinkpad.peer_query_position(Gst.Format.TIME)
            padding = 0
            if ok:
                samples = round(position * self.frame.rate / Gst.SECOND)
                padding = self.frames * self.frame.samples - ENCODER_DELAY - samples
            self.push_byte_segment()
            self.push_info_frame(min(max(padding, 0), MAX_12BIT))
        return self.srcpad.push_event(event)


GObject.type_register(LameInfoMux)


def register_element():
    """Make the element available to Gst.parse_launch. Needs Gst.init() first."""
    return Gst.Element.register(None, "lameinfomux", Gst.Rank.NONE, LameInfoMux)
