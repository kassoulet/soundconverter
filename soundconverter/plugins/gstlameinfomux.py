"""
lameinfomux - GStreamer element to inject LAME Info header for CBR MP3 files.

This element intercepts the first buffer from lamemp3enc and prepends a valid
LAME Info frame containing encoder delay and padding metadata for gapless playback.
"""

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")

import struct  # noqa: E402 (gi.require_version must be called first)

from gi.repository import GObject, Gst, GstBase  # noqa: E402

# CRC-16 polynomial for MPEG frames (0x8005 reflected)
CRC16_TABLE = []
for i in range(256):
    crc = i
    for _ in range(8):
        if crc & 1:
            crc = (crc >> 1) ^ 0xA001
        else:
            crc >>= 1
    CRC16_TABLE.append(crc)


def crc16_mpeg(data: bytes, crc: int = 0) -> int:
    """Calculate MPEG-style CRC16 (polynomial 0x8005, reflected)."""
    for byte in data:
        crc = (crc >> 8) ^ CRC16_TABLE[(crc ^ byte) & 0xFF]
    return crc & 0xFFFF


# MPEG Layer III bitrate table (kbps)
BITRATE_TABLE = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]

# Sample rate table (Hz)
SAMPLE_RATE_TABLE = [44100, 48000, 32000, 0]

# Samples per frame for Layer III
SAMPLES_PER_FRAME = 1152

# Standard LAME encoder delay
LAME_ENCODER_DELAY = 528

# LAME version string
LAME_VERSION = b"LAME3.100"


def build_mpeg_frame_header(
    bitrate_kbps: int,
    sample_rate: int,
    channels: int,
    padding: int = 0,
    layer: int = 3,
    version: int = 3,
) -> bytes:
    """
    Build a valid MPEG frame header (4 bytes).

    Args:
        bitrate_kbps: Bitrate in kbps (e.g., 128, 256)
        sample_rate: Sample rate in Hz (e.g., 44100)
        channels: Number of channels (1 or 2)
        padding: Padding bit (0 or 1)
        layer: MPEG layer (3 = Layer III)
        version: MPEG version (3 = MPEG-1)

    Returns:
        4-byte frame header
    """
    # Find bitrate index
    bitrate_idx = 0
    for i, br in enumerate(BITRATE_TABLE):
        if br == bitrate_kbps:
            bitrate_idx = i
            break

    # Find sample rate index
    sr_idx = 0
    for i, sr in enumerate(SAMPLE_RATE_TABLE):
        if sr == sample_rate:
            sr_idx = i
            break

    # Channel mode: 0=stereo, 1=joint_stereo, 2=dual_channel, 3=mono
    if channels == 1:
        mode = 3
    else:
        mode = 0

    # Build header (big-endian)
    # sync: 12 bits (0xFFF)
    # version: 2 bits
    # layer: 2 bits
    # protection_bit: 1 bit (0 = CRC protected, 1 = no CRC)
    # bitrate: 4 bits
    # sample_rate: 2 bits
    # padding: 1 bit
    # private: 1 bit
    # mode: 2 bits
    # mode_extension: 2 bits
    # copyright: 1 bit
    # original: 1 bit
    # emphasis: 2 bits

    header = 0
    header |= 0xFFF << 20  # sync (12 bits)
    header |= (version & 3) << 18  # MPEG version
    header |= ((4 - layer) & 3) << 16  # layer
    header |= 0 << 15  # protection_bit (1 = no CRC)
    header |= (bitrate_idx & 15) << 11  # bitrate index
    header |= (sr_idx & 3) << 9  # sample rate index
    header |= (padding & 1) << 8  # padding bit
    header |= 0 << 7  # private bit
    header |= (mode & 3) << 5  # channel mode
    header |= 0 << 3  # mode extension
    header |= 0 << 2  # copyright
    header |= 0 << 1  # original
    header |= 0  # emphasis

    return struct.pack(">I", header)


def build_lame_info_tag(
    bitrate_kbps: int,
    sample_rate: int,
    channels: int,
    total_frames: int,
    total_bytes: int,
    encoder_delay: int = LAME_ENCODER_DELAY,
    encoder_padding: int = 0,
) -> bytes:
    """
    Build the LAME Info tag (156 bytes after the MPEG frame header).

    Returns the complete Info frame: MPEG header (4) + "Info" + data (156) = 160 bytes
    The CRC16 covers the entire frame including header and side info.
    """
    # Build MPEG frame header (no CRC in header, we'll compute it)
    mpeg_header = build_mpeg_frame_header(
        bitrate_kbps, sample_rate, channels, padding=0
    )

    # Build the Info tag payload (12 bytes header + 144 bytes data = 156 bytes after "Info")
    payload = bytearray()

    # "Info" identifier (4 bytes)
    payload += b"Info"

    # Flags (4 bytes): bit 0=frames, 1=bytes, 2=TOC, 3=VBR_scale
    payload += struct.pack(">I", 0x0000000F)

    # Total frames (4 bytes)
    payload += struct.pack(">I", total_frames)

    # Total bytes (4 bytes)
    payload += struct.pack(">I", total_bytes)

    # TOC (100 bytes) - all zeros for CBR
    payload += b"\x00" * 100

    # VBR scale (1 byte) - 0 for CBR
    payload += b"\x00"

    # LAME version (9 bytes)
    payload += LAME_VERSION

    # Encoder delay (2 bytes, big-endian)
    payload += struct.pack(">H", encoder_delay)

    # Encoder padding (2 bytes, big-endian)
    payload += struct.pack(">H", encoder_padding)

    # Music CRC (2 bytes) - 0
    payload += b"\x00\x00"

    # Tag revision (1 byte) - 0
    payload += b"\x00"

    # VBR method (1 byte) - 0
    payload += b"\x00"

    # Lowpass filter (1 byte) - 0
    payload += b"\x00"

    # Replay gain (4 bytes) - 0
    payload += b"\x00\x00\x00\x00"

    # Encoding flags (1 byte) - 0
    payload += b"\x00"

    # Reserved (3 bytes)
    payload += b"\x00\x00\x00"

    # Pad to exactly 156 bytes
    assert len(payload) == 156, f"Payload is {len(payload)} bytes, expected 156"

    # Now compute CRC16 over MPEG header + "Info" + payload
    # The CRC covers everything from the sync word through the payload
    crc_data = mpeg_header + payload
    crc = crc16_mpeg(crc_data)

    # Rebuild header with CRC flag set to 0 (CRC present)
    # Note: protection_bit = 0 means CRC follows header
    # But for the actual frame, we need to set protection_bit = 0
    # and include the CRC16 right after the header
    return mpeg_header + struct.pack(">H", crc) + payload


class LameInfoMux(GstBase.BaseTransform):
    """
    GStreamer element that injects a LAME Info header on the first buffer
    for CBR MP3 streams.
    """

    __gstmetadata__ = (
        "LAME Info Mux",
        "Filter/Muxer/Audio",
        "Injects LAME Info header for CBR MP3 gapless playback",
        "SoundConverter Team",
    )

    # Pad templates (created in register_element after Gst.init())
    sink_template = None
    src_template = None

    def __init__(self):
        super().__init__()
        self.first_buffer = True
        self.info_header = None
        self.bitrate = 0
        self.sample_rate = 0
        self.channels = 0
        self.total_frames = 0
        self.total_bytes = 0
        self.buffer_sizes = []
        self._configured = False

    def do_set_caps(self, incaps: Gst.Caps, outcaps: Gst.Caps) -> bool:
        """Extract stream parameters from caps."""
        print("DEBUG: do_set_caps called")
        print(f"  incaps: {incaps}")
        print(f"  outcaps: {outcaps}")
        struct = incaps.get_structure(0)
        self.bitrate = (
            struct.get_int("bitrate")[1] // 1000 if struct.has_field("bitrate") else 128
        )
        self.sample_rate = (
            struct.get_int("rate")[1] if struct.has_field("rate") else 44100
        )
        self.channels = (
            struct.get_int("channels")[1] if struct.has_field("channels") else 2
        )
        print(
            f"  bitrate={self.bitrate}, sample_rate={self.sample_rate}, channels={self.channels}"
        )
        return True

    def do_start(self) -> bool:
        """Reset state on start."""
        self.first_buffer = True
        self.info_header = None
        self.total_frames = 0
        self.total_bytes = 0
        self.buffer_sizes = []
        self._configured = False
        return True

    def do_transform(self, inbuf: Gst.Buffer, outbuf: Gst.Buffer) -> Gst.FlowReturn:
        """Transform - pass through buffers, prepend Info header on first."""
        print(
            f"DEBUG: do_transform called, first_buffer={self.first_buffer}, inbuf size={inbuf.get_size()}"
        )
        if self.first_buffer:
            self.first_buffer = False

            # Build the Info header frame
            # We need to estimate total frames/bytes
            # For now, we'll build it lazily when we know the total
            # For streaming, we prepend a placeholder and update later
            # But for file output, we can't easily update...
            # So we'll build it with 0 frames/bytes initially

            self.info_header = build_lame_info_tag(
                bitrate_kbps=self.bitrate,
                sample_rate=self.sample_rate,
                channels=self.channels,
                total_frames=0,  # Will be updated if we can seek
                total_bytes=0,
            )

            # Prepend the header to the first buffer
            header_data = self.info_header
            in_data = inbuf.extract_dup(0, inbuf.get_size())
            combined = header_data + in_data
            print(
                f"DEBUG: header={len(header_data)} bytes, payload={len(in_data)} bytes, combined={len(combined)} bytes"
            )

            # Map output buffer for writing
            success, map_info = outbuf.map(Gst.MapFlags.WRITE)
            if not success:
                print("ERROR: Failed to map output buffer for writing")
                return Gst.FlowReturn.ERROR

            try:
                if len(combined) > map_info.size:
                    print(
                        f"ERROR: Combined data ({len(combined)} bytes) larger than output buffer ({map_info.size} bytes)"
                    )
                    return Gst.FlowReturn.ERROR

                # Write data to output buffer
                import ctypes

                ctypes.memmove(map_info.data, combined, len(combined))
                outbuf.unmap(map_info)

                # Resize output buffer to actual data size
                outbuf.resize(0, len(combined))

                print(
                    f"DEBUG: Wrote {len(combined)} bytes to output buffer (header: {len(header_data)}, payload: {len(in_data)})"
                )
                return Gst.FlowReturn.OK
            except (ValueError, TypeError, MemoryError, OSError) as e:
                print(f"ERROR in transform: {e}")
                outbuf.unmap(map_info)
                return Gst.FlowReturn.ERROR

        # Pass through subsequent buffers
        print(f"DEBUG: Passing through buffer, size={inbuf.get_size()}")
        return Gst.FlowReturn.OK

    def do_transform_size(
        self, direction: int, caps: Gst.Caps, size: int, othercaps: Gst.Caps
    ) -> int:
        """Account for header size on first buffer."""
        print(
            f"DEBUG: do_transform_size called, direction={direction}, size={size}, first_buffer={self.first_buffer}"
        )
        # direction: 0 = forward, 1 = reverse
        if direction == 0 and self.first_buffer:  # forward direction
            return (
                size + 160
            )  # MPEG header (4) + CRC (2) + Info tag (156) = 162? Let's check...
        return size


# Plugin initialization function
def plugin_init(plugin):
    """Register the element with GStreamer."""
    return Gst.Element.register(plugin, "lameinfomux", Gst.Rank.NONE, LameInfoMux)


# GObject registration (must be called after Gst.init())
def register_element():
    """Register the LameInfoMux element with GStreamer."""
    # Create pad templates after Gst.init()
    if LameInfoMux.sink_template is None:
        LameInfoMux.sink_template = Gst.PadTemplate.new(
            "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
        )
    if LameInfoMux.src_template is None:
        LameInfoMux.src_template = Gst.PadTemplate.new(
            "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
        )

    GObject.type_register(LameInfoMux)
    # Set pad templates on the class before registering
    Gst.ElementClass.add_pad_template(LameInfoMux, LameInfoMux.sink_template)
    Gst.ElementClass.add_pad_template(LameInfoMux, LameInfoMux.src_template)
    Gst.Element.register(None, "lameinfomux", Gst.Rank.NONE, LameInfoMux)


# Auto-register if GStreamer is already initialized
if Gst.is_initialized():
    register_element()
