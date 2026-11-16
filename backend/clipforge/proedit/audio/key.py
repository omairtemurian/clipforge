"""The musical key of a piece of music (SPEC-v3 5.4, optional): the best of
the 24 major and minor Krumhansl-Kessler key profiles to correlate with the
mean chroma, kept only above MIN_KEY_CORR."""

import numpy as np

from clipforge.proedit.beats import SAMPLE_RATE, Samples

MIN_KEY_CORR = 0.6
TONIC_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def musical_key(samples: Samples, rate: int = SAMPLE_RATE) -> str | None:
    """Return the key of music ("C major", "A minor") or None when no key
    profile correlates with its mean chroma above MIN_KEY_CORR."""
    import librosa

    chroma = librosa.feature.chroma_stft(y=samples, sr=rate)
    profile = chroma.mean(axis=1)
    if float(np.std(profile)) < 1e-9:
        return None
    best: tuple[float, str] = (-1.0, "")
    for mode, template in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
        for tonic in range(12):
            corr = float(np.corrcoef(profile, np.roll(template, tonic))[0, 1])
            best = max(best, (corr, f"{TONIC_NAMES[tonic]} {mode}"))
    return best[1] if best[0] >= MIN_KEY_CORR else None
