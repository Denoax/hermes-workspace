"""Install the optional pinned CPU transcription runtime as the desktop user.

Requires cmake, C++ compiler, ffmpeg and Python. Does not alter Qwen or start
inference. Downloaded source/model bytes are checked before use; weights stay
outside source/review archives. Reuses existing checked downloads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

REVISION = 'a8d002cfd879315632a579e73f0148d06959de36'
SOURCE_SHA = '2ffcfe0a968442ac7036aa9ff0b90811f8846ae87c7034966815c5f18f729e65'
MODEL_REVISION = '5359861c739e955e79d9a303bcbc70fb988958b1'
MODEL_SHA = '921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def download(url, destination, expected, maximum):
    if destination.exists() and not destination.is_symlink() and digest(destination) == expected:
        return
    temporary = destination.with_suffix('.part')
    try:
        with urllib.request.urlopen(url, timeout=40) as response, temporary.open('xb') as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > maximum:
                    raise ValueError('download_size_limit')
                output.write(chunk)
        if digest(temporary) != expected:
            raise ValueError('download_digest_mismatch')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path.home()/'.cache/hermes-voice-build')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise ValueError('run_as_desktop_user')
    os.umask(0o077)
    cache = args.cache
    prefix = Path.home()/'.local/share/hermes-workspace/stt'
    for path in (cache, prefix):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink() or path.stat().st_uid != os.getuid():
            raise ValueError('owned_directory_required')
    archive = cache/'source.tar.gz'
    download('https://api.github.com/repos/ggml-org/whisper.cpp/tarball/'+REVISION,
             archive, SOURCE_SHA, 20*1024*1024)
    with tarfile.open(archive) as source:
        source.extractall(cache, filter='data')
        root = cache/source.getmembers()[0].name.split('/')[0]
    build = cache/'build'
    subprocess.run(['cmake','-S',str(root),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
                    '-DBUILD_SHARED_LIBS=OFF','-DGGML_CUDA=OFF','-DGGML_VULKAN=OFF',
                    '-DWHISPER_BUILD_TESTS=OFF'], check=True)
    subprocess.run(['cmake','--build',str(build),'--target','whisper-cli','-j','4'], check=True)
    shutil.copy2(build/'bin/whisper-cli',prefix/'whisper-cli')
    shutil.copy2(root/'LICENSE',prefix/'LICENSE')
    model = prefix/'ggml-tiny.en.bin'
    download('https://huggingface.co/ggerganov/whisper.cpp/resolve/'+MODEL_REVISION+'/ggml-tiny.en.bin',
             model, MODEL_SHA, 80*1024*1024)
    record = {'source_revision':REVISION,'source_sha256':SOURCE_SHA,
              'model_repository':'ggerganov/whisper.cpp','model_revision':MODEL_REVISION,
              'files':{path.name:digest(path) for path in (prefix/'whisper-cli',model)},'CPU_only':True}
    temporary = prefix/'installation.tmp'
    temporary.write_text(json.dumps(record,indent=2)+'\n')
    temporary.replace(prefix/'installation.json')
    print('Pinned local CPU transcription installed; no model inference started.')


if __name__ == '__main__':
    main()
