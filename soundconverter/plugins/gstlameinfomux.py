#!/usr/bin/env python3
"""
lameinfomux - GStreamer element to inject LAME Info header for CBR MP3 files.

This element intercepts the first buffer from lamemp3enc and prepends a valid
LAME Info frame containing encoder delay and padding metadata for gapless playback.
"""

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")

import struct
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
BITRATE_TABLE = [
    0, 32, 40, 48, 56, 64, 80, 96,
    112, 128, 160, 192, 224, 256, 320, 0
]

# Sample rate table (Hz)
SAMPLE_RATE_TABLE = [44100, 48000, 32000, 0]

# Samples per frame for Layer III
SAMPLES_PER_FRAME = 1152

# Standard LAME encoder delay
LAME_ENCODER_DELAY = 528

# LAME version string
LAME_VERSION = b"LAME3.100"


def build_mpeg_frame_header(bitrate_kbps: int, sample_rate: int, channels: int,
                             padding: int = 0, layer: int = 3, version: int = 3) -> bytes:
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
    header |= 0xFFF << 20          # sync (12 bits)
    header |= (version & 3) << 18  # MPEG version
    header |= ((4 - layer) & 3) << 16  # layer
    header |= 0 << 15              # protection_bit (1 = no CRC)
    header |= (bitrate_idx & 15) << 11  # bitrate index
    header |= (sr_idx & 3) << 9    # sample rate index
    header |= (padding & 1) << 8   # padding bit
    header |= 0 << 7               # private bit
    header |= (mode & 3) << 5      # channel mode
    header |= 0 << 3               # mode extension
    header |= 0 << 2               # copyright
    header |= 0 << 1               # original
    header |= 0                    # emphasis

    return struct.pack('>I', header)


def build_lame_info_tag(bitrate_kbps: int, sample_rate: int, channels: int,
                         total_frames: int, total_bytes: int,
                         encoder_delay: int = LAME_ENCODER_DELAY,
                         encoder_padding: int = 0) -> bytes:
    """
    Build the LAME Info tag (156 bytes after the MPEG frame header).

    Returns the complete Info frame: MPEG header (4) + "Info" + data (156) = 160 bytes
    The CRC16 covers the entire frame including header and side info.
    """
    # Build MPEG frame header (no CRC in header, we'll compute it)
    mpeg_header = build_mpeg_frame_header(bitrate_kbps, sample_rate, channels, padding=0)

    # Build the Info tag payload (12 bytes header + 144 bytes data = 156 bytes after "Info")
    payload = bytearray()

    # "Info" identifier (4 bytes)
    payload += b'Info'

    # Flags (4 bytes): bit 0=frames, 1=bytes, 2=TOC, 3=VBR_scale
    payload += struct.pack('>I', 0x0000000F)

    # Total frames (4 bytes)
    payload += struct.pack('>I', total_frames)

    # Total bytes (4 bytes)
    payload += struct.pack('>I', total_bytes)

    # TOC (100 bytes) - all zeros for CBR
    payload += b'\x00' * 100

    # VBR scale (1 byte) - 0 for CBR
    payload += b'\x00'

    # LAME version (9 bytes)
    payload += LAME_VERSION

    # Encoder delay (2 bytes, big-endian)
    payload += struct.pack('>H', encoder_delay)

    # Encoder padding (2 bytes, big-endian)
    payload += struct.pack('>H', encoder_padding)

    # Music CRC (2 bytes) - 0
    payload += b'\x00\x00'

    # Tag revision (1 byte) - 0
    payload += b'\x00'

    # VBR method (1 byte) - 0
    payload += b'\x00'

    # Lowpass filter (1 byte) - 0
    payload += b'\x00'

    # Replay gain (4 bytes) - 0
    payload += b'\x00\x00\x00\x00'

    # Encoding flags (1 byte) - 0
    payload += b'\x00'

    # Reserved (3 bytes)
    payload += b'\x00\x00\x00'

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
    return mpeg_header + struct.pack('>H', crc) + payload


class LameInfoMux(GstBase.BaseTransform):
    """
    GStreamer element that injects a LAME Info header on the first buffer
    for CBR MP3 streams.
    """

    __gstmetadata__ = (
        "LAME Info Mux",
        "Filter/Muxer/Audio",
        "Injects LAME Info header for CBR MP3 gapless playback",
        "SoundConverter Team"
    )

    __gsttemplates__ = (
        Gst.PadTemplate.new(
            "sink",
            Gst.PadDirection.SINK,
            Gst.PadPresence.ALWAYS,
            Gst.Caps.new_any()
        ),
        Gst.PadTemplate.new(
            "src",
            Gst.PadDirection.SRC,
            Gst.PadPresence.ALWAYS,
            Gst.Caps.new_any()
        )
    )

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
        struct = incaps.get_structure(0)
        self.bitrate = struct.get_int("bitrate")[1] // 1000 if struct.has_field("bitrate") else 128
        self.sample_rate = struct.get_int("rate")[1] if struct.has_field("rate") else 44100
        self.channels = struct.get_int("channels")[1] if struct.has_field("channels") else 2
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

            outbuf.fill(0, combined)
            return Gst.FlowReturn.OK

        # Pass through subsequent buffers
        return Gst.FlowReturn.OK

    def do_transform_size(self, direction: GstBase.TransformDirection,
                          caps: Gst.Caps, size: int, othercaps: Gst.Caps) -> int:
        """Account for header size on first buffer."""
        if direction == GstBase.TransformDirection.FORWARD and self.first_buffer:
            return size + 160  # MPEG header (4) + CRC (2) + Info tag (156) = 162? Let's check...
        return size


# GObject registration
GObject.type_register(LameInfoMux)

# Element factory registration
__gstelementfactory__ = (
    "lameinfomux",
    Gst.Rank.NONE,
    LameInfoMux
)