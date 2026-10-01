"""Compõe uma trilha instrumental sincronizada com a edição (sem depender de música externa).

Seções (em segundos do vídeo final):
  0 .. acao          pads de abertura (pôr do sol)
  acao .. climax     batida + baixo + arpejo (navegação e saltos)
  climax .. sol      impacto e meia-batida (câmera lenta do melhor momento)
  sol .. fim         pads e arpejo suave (pôr do sol), fade-out

Uso: python editor/trilha.py --duracao 36.6 --acao 3.8 --climax 23.6 --sol 27.5
Saída: musica/trilha.wav
"""
import argparse
import wave

import numpy as np

from analisar import RAIZ

SR = 44100
# Am - F - C - G (lá menor), notas em Hz
ACORDES = [
    [220.00, 261.63, 329.63],
    [174.61, 220.00, 261.63],
    [261.63, 329.63, 392.00],
    [196.00, 246.94, 293.66],
]
BAIXO = [55.00, 43.65, 65.41, 49.00]


def envelope(n, ataque, queda):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-t / queda)


def passa_baixa(x, corte):
    a = np.exp(-2 * np.pi * corte / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def serra(f, t):
    return 2 * ((f * t) % 1) - 1


def reverb(x, mistura=0.3):
    saida = x.copy()
    for atraso, ganho in [(0.0297, 0.6), (0.0371, 0.55), (0.0411, 0.5), (0.0437, 0.45)]:
        d = int(atraso * SR)
        eco = np.zeros_like(x)
        for k in range(1, 12):
            if d * k >= len(x):
                break
            eco[d * k:] += x[:-d * k] * ganho ** k
        saida += eco * mistura / 4
    return saida


def compor(duracao, acao, climax, sol, bpm):
    n = int(duracao * SR)
    t = np.arange(n) / SR
    tempo = 60 / bpm
    compasso = tempo * 4
    pad = np.zeros(n)
    baixo = np.zeros(n)
    arpejo = np.zeros(n)
    bumbo = np.zeros(n)
    chimbal = np.zeros(n)
    rng = np.random.default_rng(7)

    # Pads: um acorde por compasso, a partir de t=0, alinhados à grade que começa em `acao`
    origem = acao - np.ceil(acao / compasso) * compasso
    k = 0
    inicio = origem
    while inicio < duracao:
        i0, i1 = max(0, int(inicio * SR)), min(n, int((inicio + compasso) * SR))
        if i1 > i0:
            tt = t[i0:i1]
            acorde = ACORDES[k % 4]
            som = sum(serra(f * d, tt) for f in acorde for d in (0.997, 1.003)) / 6
            janela = np.minimum(1, np.minimum((tt - inicio) / 0.08, (inicio + compasso - tt) / 0.08).clip(0))
            pad[i0:i1] += som * janela
            if acao <= inicio < sol:
                env = envelope(i1 - i0, 0.01, compasso * 0.6)
                baixo[i0:i1] += np.sin(2 * np.pi * BAIXO[k % 4] * tt) * env
            # arpejo em colcheias
            for passo in range(8):
                p0 = inicio + passo * tempo / 2
                if p0 < acao * 0.5 or p0 >= duracao:
                    continue
                j0 = int(p0 * SR)
                m = min(int(0.45 * SR), n - j0)
                if j0 < 0 or m <= 0:
                    continue
                f = acorde[[0, 1, 2, 1, 2, 0, 1, 2][passo]] * 2
                tri = 2 * np.abs(2 * ((f * np.arange(m) / SR) % 1) - 1) - 1
                arpejo[j0:j0 + m] += tri * envelope(m, 0.003, 0.12)
        inicio += compasso
        k += 1

    # Bateria: entra em `acao`; no clímax vira meia-batida com impacto; sai no pôr do sol
    def bater(alvo, t0, som):
        j0 = int(t0 * SR)
        m = min(len(som), n - j0)
        if 0 <= j0 < n:
            alvo[j0:j0 + m] += som[:m]

    m = int(0.35 * SR)
    tb = np.arange(m) / SR
    som_bumbo = np.sin(2 * np.pi * (45 * tb + 90 * (1 - np.exp(-tb * 30)) / 30)) * envelope(m, 0.001, 0.12)
    som_chimbal = rng.uniform(-1, 1, int(0.05 * SR))
    som_chimbal = (som_chimbal - passa_baixa(som_chimbal, 6000)) * envelope(len(som_chimbal), 0.001, 0.015)
    batida = acao
    while batida < sol - 0.05:
        no_climax = climax <= batida < sol
        indice = int(round((batida - acao) / tempo))
        if not no_climax or indice % 2 == 0:
            bater(bumbo, batida, som_bumbo)
        if not no_climax:
            bater(chimbal, batida + tempo / 2, som_chimbal)
            if indice % 4 in (1, 3):  # palmas no 2 e 4
                bater(chimbal, batida, som_chimbal * 2.5)
        batida += tempo
    # impacto no clímax (bumbo grave + ruído de onda)
    m = int(2.5 * SR)
    ruido = passa_baixa(rng.uniform(-1, 1, m), 900) * envelope(m, 0.005, 0.8) * 3
    bater(bumbo, climax, som_bumbo * 1.6)
    bater(chimbal, climax, ruido)

    # Mixagem e dinâmica por seção
    pad = passa_baixa(pad, 1400)
    nivel_pad = np.interp(t, [0, acao, climax, sol, duracao], [0.55, 0.35, 0.45, 0.6, 0.6])
    nivel_arp = np.interp(t, [0, acao, sol, duracao], [0.10, 0.22, 0.16, 0.10])
    mix = (pad * nivel_pad + baixo * 0.32 + arpejo * nivel_arp + bumbo * 0.6 + chimbal * 0.12)
    mix = reverb(mix, 0.35)
    mix *= np.minimum(1, t / 1.5) * np.minimum(1, (duracao - t) / 3.0).clip(0)
    mix = np.tanh(mix * 1.2)
    mix /= np.abs(mix).max() + 1e-9
    return (mix * 0.89 * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duracao", type=float, required=True)
    ap.add_argument("--acao", type=float, required=True)
    ap.add_argument("--climax", type=float, required=True)
    ap.add_argument("--sol", type=float, required=True)
    ap.add_argument("--bpm", type=float, default=0, help="0 = encaixa 8 compassos entre ação e clímax")
    args = ap.parse_args()
    bpm = args.bpm or 60 / ((args.climax - args.acao) / 32)
    audio = compor(args.duracao, args.acao, args.climax, args.sol, bpm)
    destino = RAIZ / "musica" / "trilha.wav"
    destino.parent.mkdir(exist_ok=True)
    estereo = np.repeat(audio[:, None], 2, axis=1)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(estereo.tobytes())
    print(f"{destino.relative_to(RAIZ)} ({args.duracao:.1f}s, {bpm:.1f} bpm)")


if __name__ == "__main__":
    main()
