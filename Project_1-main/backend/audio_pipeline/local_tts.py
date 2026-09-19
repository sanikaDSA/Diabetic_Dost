import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("local_tts")


def synthesize_local_speech(text: str, output_wav_path: Path, language: str = "hi-IN") -> bool:
    """
    Synthesizes clean speech locally on Windows using Windows Speech Synthesis / SAPI (Male voice).
    Never outputs artificial sine beeps or noisy waveforms.
    """
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    out_str = str(output_wav_path.resolve()).replace("\\", "\\\\")

    # Clean text of quotes that might break PowerShell script
    clean_txt = text.replace('"', ' ').replace("'", " ").replace("\n", " ").strip()

    # Polite, gentle doctor-companion voice pacing
    ps_command = (
        f'Add-Type -AssemblyName System.Speech; '
        f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        f'$voices = $s.GetInstalledVoices(); '
        f'foreach ($v in $voices) {{ if ($v.VoiceInfo.Gender -eq "Male" -or $v.VoiceInfo.Culture.Name -like "*IN*") {{ $s.SelectVoice($v.VoiceInfo.Name); break; }} }} '
        f'$s.Rate = 0; '        # Steady, consistent natural doctor pacing across all turns
        f'$s.Volume = 100; '    # Clear, uniform listening volume
        f'$s.SetOutputToWaveFile("{out_str}"); '
        f'$s.Speak("{clean_txt}"); '
        f'$s.Dispose()'
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_command],
            check=True,
            capture_output=True,
            timeout=8
        )
        if output_wav_path.exists() and output_wav_path.stat().st_size > 500:
            logger.info(f"Synthesized local speech audio: {output_wav_path.name} ({output_wav_path.stat().st_size} bytes)")
            return True
    except Exception as e:
        logger.warning(f"PowerShell SAPI TTS fallback: {e}")

    # If SAPI failed, return False so the frontend cleanly uses native browser Neural SpeechSynthesis
    if output_wav_path.exists():
        try:
            output_wav_path.unlink()
        except Exception:
            pass
    return False


