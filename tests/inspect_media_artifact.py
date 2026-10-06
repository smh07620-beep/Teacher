"""Inspect the actual isolated S3 object; never seed generated artifacts."""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
import boto3

assert os.environ.get("TEACHER_E2E_TEST_MODE") == "1"
assert os.environ["R2_ENDPOINT_URL"] == "http://127.0.0.1:9001"
key, kind = sys.argv[1:3]
client = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="us-east-1")
obj = client.get_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key)
data = obj["Body"].read()
assert len(data) > 1024
result = {"bytes": len(data), "mime": obj["ContentType"], "metadata": obj.get("Metadata", {}),
          "sha256": hashlib.sha256(data).hexdigest()}
if kind == "wav":
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data)) as audio:
        result.update(rate=audio.getframerate(), channels=audio.getnchannels(), frames=audio.getnframes(),
                      duration=audio.getnframes()/audio.getframerate())
    assert result["rate"] > 0 and result["channels"] > 0 and result["duration"] > 0
elif kind == "mp4":
    assert b"ftyp" in data[:32]
    with tempfile.TemporaryDirectory() as root:
        target = Path(root) / "artifact.mp4"
        target.write_bytes(data)
        probe = subprocess.run([os.environ.get("FFMPEG_PATH", "ffmpeg"), "-i", str(target), "-f", "null", "-"], capture_output=True)
        assert probe.returncode == 0, probe.stderr.decode(errors="replace")
        diagnostic = probe.stderr.decode(errors="replace")
        duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", diagnostic)
        assert duration, "FFmpeg could not read MP4 duration"
        hours, minutes, seconds = map(float, duration.groups())
        result["duration"] = hours * 3600 + minutes * 60 + seconds
        assert result["duration"] > 0
        result["decoded"] = True
else:
    raise ValueError(kind)
print(json.dumps(result))
