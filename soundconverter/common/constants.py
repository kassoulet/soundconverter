from enum import Enum


class MimeType(str, Enum):
    OGG_VORBIS = "audio/x-vorbis"
    MPEG = "audio/mpeg"
    FLAC = "audio/x-flac"
    WAV = "audio/x-wav"
    M4A = "audio/x-m4a"
    OPUS = "audio/ogg; codecs=opus"
    WMA = "audio/x-ms-wma"


class EncoderName(str, Enum):
    VORBISENC = "vorbisenc"
    LAMEMP3ENC = "lamemp3enc"
    FLACENC = "flacenc"
    WAVENC = "wavenc"
    FDKAACENC = "fdkaacenc"
    FAAC = "faac"
    AVENC_AAC = "avenc_aac"
    OPUSENC = "opusenc"
    AVENC_WMAV2 = "avenc_wmav2"
    ASFMUX = "asfmux"
    OGGMUX = "oggmux"
    ID3MUX = "id3mux"
    ID3V2MUX = "id3v2mux"
    XINGMUX = "xingmux"
    MP4MUX = "mp4mux"


class QualityTabPage(Enum):
    OGG_VORBIS = 0
    MPEG = 1
    FLAC = 2
    WAV = 3
    M4A = 4
    OPUS = 5
    WMA = 6


class Mp3Mode(str, Enum):
    CBR = "cbr"
    ABR = "abr"
    VBR = "vbr"


class Mp3QualitySetting(str, Enum):
    CBR = "mp3-cbr-quality"
    ABR = "mp3-abr-quality"
    VBR = "mp3-vbr-quality"


EXIT_CODE_NO_AUDIO_FILES = 2
