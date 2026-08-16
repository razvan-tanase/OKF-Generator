from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class FormatRule:
    format: str
    media_type: str
    family: str
    route: str
    text: bool = False
    signature_family: str | None = None


FORMAT_BY_EXTENSION: dict[str, FormatRule] = {
    ".md": FormatRule("markdown", "text/markdown", "text", "markdown", text=True),
    ".markdown": FormatRule("markdown", "text/markdown", "text", "markdown", text=True),
    ".mdx": FormatRule("mdx", "text/mdx", "text", "markup", text=True),
    ".txt": FormatRule("text", "text/plain", "text", "text", text=True),
    ".rst": FormatRule("rst", "text/x-rst", "text", "markup", text=True),
    ".tex": FormatRule("latex", "application/x-latex", "text", "markup", text=True),
    ".html": FormatRule("html", "text/html", "text", "markup", text=True),
    ".htm": FormatRule("html", "text/html", "text", "markup", text=True),
    ".xml": FormatRule("xml", "application/xml", "data", "markup", text=True),
    ".svg": FormatRule("svg", "image/svg+xml", "image", "markup", text=True),
    ".json": FormatRule("json", "application/json", "data", "structured-text", text=True),
    ".jsonl": FormatRule("jsonl", "application/x-ndjson", "data", "structured-text", text=True),
    ".yaml": FormatRule("yaml", "application/yaml", "data", "structured-text", text=True),
    ".yml": FormatRule("yaml", "application/yaml", "data", "structured-text", text=True),
    ".toml": FormatRule("toml", "application/toml", "data", "structured-text", text=True),
    ".csv": FormatRule("csv", "text/csv", "data", "structured-text", text=True),
    ".tsv": FormatRule("tsv", "text/tab-separated-values", "data", "structured-text", text=True),
    ".sql": FormatRule("sql", "application/sql", "code", "text-source", text=True),
    ".py": FormatRule("python", "text/x-python", "code", "text-source", text=True),
    ".js": FormatRule("javascript", "text/javascript", "code", "text-source", text=True),
    ".mjs": FormatRule("javascript", "text/javascript", "code", "text-source", text=True),
    ".cjs": FormatRule("javascript", "text/javascript", "code", "text-source", text=True),
    ".ts": FormatRule("typescript", "text/typescript", "code", "text-source", text=True),
    ".tsx": FormatRule("tsx", "text/tsx", "code", "text-source", text=True),
    ".jsx": FormatRule("jsx", "text/jsx", "code", "text-source", text=True),
    ".java": FormatRule("java", "text/x-java-source", "code", "text-source", text=True),
    ".go": FormatRule("go", "text/x-go", "code", "text-source", text=True),
    ".rs": FormatRule("rust", "text/x-rust", "code", "text-source", text=True),
    ".c": FormatRule("c", "text/x-c", "code", "text-source", text=True),
    ".h": FormatRule("c-header", "text/x-c", "code", "text-source", text=True),
    ".cpp": FormatRule("cpp", "text/x-c++", "code", "text-source", text=True),
    ".cc": FormatRule("cpp", "text/x-c++", "code", "text-source", text=True),
    ".hpp": FormatRule("cpp-header", "text/x-c++", "code", "text-source", text=True),
    ".sh": FormatRule("shell", "application/x-sh", "code", "text-source", text=True),
    ".ps1": FormatRule("powershell", "text/x-powershell", "code", "text-source", text=True),
    ".ipynb": FormatRule("jupyter-notebook", "application/x-ipynb+json", "data", "structured-text", text=True),
    ".pdf": FormatRule("pdf", "application/pdf", "document", "pdf", signature_family="pdf"),
    ".docx": FormatRule("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document", "office", signature_family="zip"),
    ".xlsx": FormatRule("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "data", "office", signature_family="zip"),
    ".pptx": FormatRule("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "document", "office", signature_family="zip"),
    ".odt": FormatRule("odt", "application/vnd.oasis.opendocument.text", "document", "office", signature_family="zip"),
    ".ods": FormatRule("ods", "application/vnd.oasis.opendocument.spreadsheet", "data", "office", signature_family="zip"),
    ".odp": FormatRule("odp", "application/vnd.oasis.opendocument.presentation", "document", "office", signature_family="zip"),
    ".epub": FormatRule("epub", "application/epub+zip", "document", "archive-document", signature_family="zip"),
    ".doc": FormatRule("doc", "application/msword", "document", "office", signature_family="ole"),
    ".xls": FormatRule("xls", "application/vnd.ms-excel", "data", "office", signature_family="ole"),
    ".ppt": FormatRule("ppt", "application/vnd.ms-powerpoint", "document", "office", signature_family="ole"),
    ".rtf": FormatRule("rtf", "application/rtf", "document", "rich-text", signature_family="rtf"),
    ".zip": FormatRule("zip", "application/zip", "archive", "archive", signature_family="zip"),
    ".gz": FormatRule("gzip", "application/gzip", "archive", "archive", signature_family="gzip"),
    ".bz2": FormatRule("bzip2", "application/x-bzip2", "archive", "archive", signature_family="bzip2"),
    ".xz": FormatRule("xz", "application/x-xz", "archive", "archive", signature_family="xz"),
    ".7z": FormatRule("7z", "application/x-7z-compressed", "archive", "archive", signature_family="7z"),
    ".rar": FormatRule("rar", "application/vnd.rar", "archive", "archive", signature_family="rar"),
    ".tar": FormatRule("tar", "application/x-tar", "archive", "archive", signature_family="tar"),
    ".png": FormatRule("png", "image/png", "image", "image", signature_family="png"),
    ".jpg": FormatRule("jpeg", "image/jpeg", "image", "image", signature_family="jpeg"),
    ".jpeg": FormatRule("jpeg", "image/jpeg", "image", "image", signature_family="jpeg"),
    ".gif": FormatRule("gif", "image/gif", "image", "image", signature_family="gif"),
    ".webp": FormatRule("webp", "image/webp", "image", "image", signature_family="webp"),
    ".tif": FormatRule("tiff", "image/tiff", "image", "image", signature_family="tiff"),
    ".tiff": FormatRule("tiff", "image/tiff", "image", "image", signature_family="tiff"),
    ".wav": FormatRule("wav", "audio/wav", "audio", "audio", signature_family="wav"),
    ".mp3": FormatRule("mp3", "audio/mpeg", "audio", "audio", signature_family="mp3"),
    ".ogg": FormatRule("ogg", "application/ogg", "audio-video", "media", signature_family="ogg"),
    ".mp4": FormatRule("mp4", "video/mp4", "video", "video", signature_family="mp4"),
    ".sqlite": FormatRule("sqlite", "application/vnd.sqlite3", "database", "database", signature_family="sqlite"),
    ".sqlite3": FormatRule("sqlite", "application/vnd.sqlite3", "database", "database", signature_family="sqlite"),
    ".db": FormatRule("sqlite", "application/vnd.sqlite3", "database", "database", signature_family="sqlite"),
    ".parquet": FormatRule("parquet", "application/vnd.apache.parquet", "data", "binary-data", signature_family="parquet"),
}


SIGNATURE_RULES: tuple[tuple[str, Callable[[bytes], bool], FormatRule], ...] = (
    ("pdf", lambda b: b.startswith(b"%PDF-"), FORMAT_BY_EXTENSION[".pdf"]),
    ("png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"), FORMAT_BY_EXTENSION[".png"]),
    ("jpeg", lambda b: b.startswith(b"\xff\xd8\xff"), FORMAT_BY_EXTENSION[".jpg"]),
    ("gif", lambda b: b.startswith((b"GIF87a", b"GIF89a")), FORMAT_BY_EXTENSION[".gif"]),
    ("webp", lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP", FORMAT_BY_EXTENSION[".webp"]),
    ("tiff", lambda b: b.startswith((b"II*\x00", b"MM\x00*")), FORMAT_BY_EXTENSION[".tif"]),
    ("gzip", lambda b: b.startswith(b"\x1f\x8b"), FORMAT_BY_EXTENSION[".gz"]),
    ("bzip2", lambda b: b.startswith(b"BZh"), FORMAT_BY_EXTENSION[".bz2"]),
    ("xz", lambda b: b.startswith(b"\xfd7zXZ\x00"), FORMAT_BY_EXTENSION[".xz"]),
    ("7z", lambda b: b.startswith(b"7z\xbc\xaf\x27\x1c"), FORMAT_BY_EXTENSION[".7z"]),
    ("rar", lambda b: b.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")), FORMAT_BY_EXTENSION[".rar"]),
    ("rtf", lambda b: b.startswith(b"{\\rtf"), FORMAT_BY_EXTENSION[".rtf"]),
    ("sqlite", lambda b: b.startswith(b"SQLite format 3\x00"), FORMAT_BY_EXTENSION[".sqlite"]),
    ("parquet", lambda b: b.startswith(b"PAR1"), FORMAT_BY_EXTENSION[".parquet"]),
    ("wav", lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WAVE", FORMAT_BY_EXTENSION[".wav"]),
    ("ogg", lambda b: b.startswith(b"OggS"), FORMAT_BY_EXTENSION[".ogg"]),
    ("mp3", lambda b: b.startswith(b"ID3") or (len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0), FORMAT_BY_EXTENSION[".mp3"]),
    ("mp4", lambda b: len(b) >= 12 and b[4:8] == b"ftyp", FORMAT_BY_EXTENSION[".mp4"]),
)

