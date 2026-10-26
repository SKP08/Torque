"""
Acoustic echo cancellation (partitioned-block frequency-domain adaptive filter).

While Torque talks, the microphone hears Torque. We know exactly what the speakers
play (the reference), so we learn the room's echo path and subtract our own voice;
what is left is you. Pure numpy, ~0.3 ms per 32 ms block.

This is classic NLMS adaptation in the frequency domain (PBFDAF). It handles a
fixed delay (device buffering) and a room response up to `partitions * block`
samples. It cannot cancel non-linear speaker distortion, so headphones are still
the most reliable setup.
"""

import numpy as np

BLOCK = 512


class EchoCanceller:

    def __init__(self, block=BLOCK, partitions=16, mu=0.35, fast_mu=0.35, fast_blocks=90, min_reference=1e-4):
        self.block = block
        self.partitions = partitions
        self.mu = mu
        self.fast_mu = fast_mu                       # bigger steps while the filter is still empty
        self.fast_blocks = fast_blocks               # ~3 s of reference audio
        self.trained_blocks = 0
        self.min_reference = min_reference           # RMS below which the reference is "silence"

        bins = block + 1

        self._weights = np.zeros((partitions, bins), dtype=np.complex128)
        self._history = np.zeros((partitions, bins), dtype=np.complex128)
        self._ref_prev = np.zeros(block)
        self._power = np.full(bins, 1e-6)
        self.echo_estimate_rms = 0.0                 # of the last block: how loud our own voice is

    def reset(self):
        self._weights[:] = 0
        self._history[:] = 0
        self._ref_prev[:] = 0
        self._power[:] = 1e-6
        self.echo_estimate_rms = 0.0
        self.trained_blocks = 0

    @property
    def converged(self) -> bool:
        return self.trained_blocks >= self.fast_blocks

    def process(self, mic, reference):
        """mic, reference: float arrays of `block` samples in [-1, 1]. Returns the residual."""

        block = self.block
        mic = np.asarray(mic, dtype=np.float64)
        reference = np.asarray(reference, dtype=np.float64)

        spectrum = np.fft.rfft(np.concatenate([self._ref_prev, reference]))
        self._ref_prev = reference.copy()

        self._history = np.roll(self._history, 1, axis=0)
        self._history[0] = spectrum

        estimate = np.fft.irfft((self._weights * self._history).sum(axis=0))[block:]
        residual = mic - estimate

        self.echo_estimate_rms = float(np.sqrt(np.mean(estimate * estimate)))

        if float(np.sqrt(np.mean(reference * reference))) < self.min_reference:
            return residual                              # nothing playing: nothing to learn

        # Normalised update. Power is smoothed so one loud block doesn't throw the filter.
        power = (self._history.real ** 2 + self._history.imag ** 2).sum(axis=0)
        self._power = 0.9 * self._power + 0.1 * power
        norm = self._power + 1e-3

        error = np.fft.rfft(np.concatenate([np.zeros(block), residual]))
        gradient = np.conj(self._history) * error / norm

        # Constrain each partition to a causal block (zero the wrapped half).
        time_domain = np.fft.irfft(gradient, axis=1)
        time_domain[:, block:] = 0
        step = self.mu if self.converged else self.fast_mu
        self.trained_blocks += 1
        self._weights += step * np.fft.rfft(time_domain, axis=1)

        return residual
