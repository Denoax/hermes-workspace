"""Read bounded GGUF metadata without loading tensors or executing model code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

FORMATS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}


def read_metadata(path):
    with Path(path).open("rb") as source:
        size = Path(path).stat().st_size

        def read(count):
            if count < 0 or count > 16 * 1024 * 1024 or source.tell() + count > size:
                raise ValueError("metadata_size_limit")
            result = source.read(count)
            if len(result) != count:
                raise ValueError("truncated_metadata")
            return result

        def integer():
            return struct.unpack("<Q", read(8))[0]

        def string():
            return read(integer())

        def value(kind, capture, depth=0):
            if depth > 2:
                raise ValueError("nested_metadata_limit")
            if kind in FORMATS:
                fmt = "<" + FORMATS[kind]
                result = struct.unpack(fmt, read(struct.calcsize(fmt)))[0]
                return result if capture else None
            if kind == 8:
                result = string()
                return result.decode("utf-8") if capture else None
            if kind == 9:
                element = struct.unpack("<I", read(4))[0]
                count = integer()
                if count > 1_000_000:
                    raise ValueError("array_count_limit")
                for _ in range(count):
                    value(element, False, depth + 1)
                return {"array_type": element, "count": count} if capture else None
            raise ValueError("unknown_metadata_type")

        if read(4) != b"GGUF":
            raise ValueError("not_GGUF")
        version = struct.unpack("<I", read(4))[0]
        if version not in (2, 3):
            raise ValueError("unsupported_GGUF_version")
        tensors, entries = integer(), integer()
        if entries > 10000:
            raise ValueError("metadata_count_limit")
        selected = {}
        tokenizer_fields = {}
        for _ in range(entries):
            key = string().decode("utf-8")
            kind = struct.unpack("<I", read(4))[0]
            capture = key.startswith("general.") or key in ("tokenizer.ggml.model", "tokenizer.ggml.pre", "tokenizer.chat_template")
            capture |= key.endswith(("context_length", "block_count", "expert_count", "expert_used_count"))
            capture |= key in ('tokenizer.ggml.add_bos_token', 'tokenizer.ggml.add_eos_token',
                              'tokenizer.ggml.bos_token_id', 'tokenizer.ggml.eos_token_id')
            start = source.tell()
            result = value(kind, capture)
            end = source.tell()
            if key.startswith('tokenizer.'):
                # Hash complete serialized vocabulary/merges/special-token data;
                # family labels alone do not prove tokenizer compatibility.
                checksum = hashlib.sha256(struct.pack('<I', kind))
                source.seek(start)
                remaining = end-start
                while remaining:
                    chunk = read(min(remaining, 4*1024*1024))
                    checksum.update(chunk)
                    remaining -= len(chunk)
                tokenizer_fields[key] = {'sha256': checksum.hexdigest(), 'serialized_bytes': end-start}
            if key == "tokenizer.chat_template":
                result = {"sha256": hashlib.sha256(result.encode()).hexdigest(), "utf8_bytes": len(result.encode())}
            if capture:
                selected[key] = result
        return {"version": version, "tensor_count": tensors, "metadata_entries": entries,
                "selected_metadata": selected, 'complete_tokenizer_field_hashes': tokenizer_fields}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(read_metadata(args.path), indent=2))
