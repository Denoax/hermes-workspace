"""Fixed local CPU decoder/transcriber; never a model-authored command."""
import hashlib,json,os,subprocess,tempfile,wave
from pathlib import Path

ROOT=Path.home()/'.local/share/hermes-workspace/stt'


def available():
    try:
        lock=json.loads((ROOT/'installation.json').read_text())
        for name,digest in lock['files'].items():
            path=ROOT/name
            if path.is_symlink() or not path.is_file() or path.stat().st_uid!=os.getuid():return False
            with path.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=digest:return False
        return True
    except (OSError,KeyError,ValueError):return False


def transcribe(source):
    if not available():raise RuntimeError('local_transcription_not_installed')
    with tempfile.TemporaryDirectory(prefix='hermes-voice-') as directory:
        wav=Path(directory)/'decoded.wav';out=Path(directory)/'transcript'
        subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-t','120','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],check=True,capture_output=True,timeout=30)
        import array
        with wave.open(str(wav)) as audio:
            duration=audio.getnframes()/audio.getframerate();samples=array.array('h',audio.readframes(audio.getnframes()))
        bars=[max((abs(x)/32768 for x in samples[i*len(samples)//40:(i+1)*len(samples)//40]),default=0) for i in range(40)]
        if not .2<=duration<=120:raise ValueError('voice_duration_limit')
        subprocess.run([str(ROOT/'whisper-cli'),'-m',str(ROOT/'ggml-tiny.en.bin'),'-f',str(wav),'-otxt','-of',str(out),'-t','4','-ng','-nt'],check=True,capture_output=True,timeout=180)
        transcript=out.with_suffix('.txt').read_text().strip()
        if not transcript or len(transcript.encode())>12000:raise ValueError('no_usable_local_transcript')
        return {'transcript':transcript,'duration':duration,'waveform':bars,'method':'local_whisper_cpp_CPU'}
