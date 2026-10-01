"""Analisa os vídeos brutos e encontra saltos, pôr do sol e trechos de navegação.

Para cada vídeo em videos/ gera:
  analise/<nome>.json  -> sinais por instante (movimento, subida, pôr do sol) e candidatos
  analise/<nome>.jpg   -> folha de contato com miniaturas e notas, para revisão visual
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
PASTA_VIDEOS = RAIZ / "videos"
PASTA_ANALISE = RAIZ / "analise"
EXTENSOES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".webm"}
AMOSTRAS_POR_SEG = 6
LARGURA_ANALISE = 240


def info_video(caminho):
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,avg_frame_rate:stream_tags=rotate:stream_side_data=rotation:format=duration",
         "-of", "json", str(caminho)],
        capture_output=True, text=True, check=True).stdout
    dados = json.loads(saida)
    video = next(s for s in dados["streams"] if s["codec_type"] == "video")
    num, den = video.get("avg_frame_rate", "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    return {
        "duracao": float(dados["format"]["duration"]),
        "fps": fps,
        "tem_audio": any(s["codec_type"] == "audio" for s in dados["streams"]),
    }


def ler_quadros(caminho, duracao):
    """Decodifica via ffmpeg (respeita a rotação de vídeos de celular) em baixa resolução."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(caminho), "-vf",
         f"fps={AMOSTRAS_POR_SEG},scale={LARGURA_ANALISE}:-2", "-f", "image2pipe",
         "-vcodec", "bmp", "-"], capture_output=True, check=True)
    dados = proc.stdout
    quadros, i = [], 0
    while i < len(dados):
        tamanho = int.from_bytes(dados[i + 2:i + 6], "little")
        img = cv2.imdecode(np.frombuffer(dados[i:i + tamanho], np.uint8), cv2.IMREAD_COLOR)
        quadros.append(img)
        i += tamanho
    return quadros


def suavizar(x, janela):
    if janela <= 1 or len(x) < janela:
        return np.asarray(x, float)
    nucleo = np.ones(janela) / janela
    return np.convolve(np.pad(x, (janela // 2, janela - 1 - janela // 2), mode="edge"), nucleo, "valid")


def nota_por_do_sol(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    ceu = slice(0, int(img.shape[0] * 0.65))
    quente = ((h[ceu] < 22) | (h[ceu] > 165)) & (s[ceu] > 70) & (v[ceu] > 60)
    brilho = v.mean() / 255
    # pôr do sol: céu quente e cena mais escura que o meio-dia
    return float(quente.mean() * (1.25 - 0.5 * brilho))


def sinais_movimento(anterior, atual):
    """Fluxo óptico: energia de movimento e deslocamento vertical do objeto em destaque.

    Subtrai o movimento da câmera (mediana do fluxo); o que sobra nos pixels mais
    rápidos é o kitesurfista. vy negativo = subindo na imagem.
    """
    a = cv2.cvtColor(anterior, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(atual, cv2.COLOR_BGR2GRAY)
    fluxo = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    camera = np.median(fluxo.reshape(-1, 2), axis=0)
    resto = fluxo - camera
    mag = np.linalg.norm(resto, axis=2)
    corte = np.percentile(mag, 98)
    destaque = mag >= max(corte, 0.5)
    vy = float(resto[..., 1][destaque].mean()) if destaque.any() else 0.0
    return float(mag.mean()), vy, float(np.abs(camera).sum())


def encontrar_saltos(t, altura, energia, dt):
    """Picos de altura (subida seguida de descida) entre 0,6 e 6 s."""
    candidatos = []
    n = len(altura)
    raio = int(2.5 / dt)
    for i in range(1, n - 1):
        ini, fim = max(0, i - raio), min(n, i + raio + 1)
        if altura[i] < altura[ini:fim].max():
            continue
        antes = altura[i] - altura[ini:i + 1].min()
        depois = altura[i] - altura[i:fim].min()
        proeminencia = min(antes, depois)
        if proeminencia <= 0:
            continue
        nota = proeminencia * (1 + energia[ini:fim].mean())
        candidatos.append({"pico": float(t[i]), "nota": float(nota)})
    candidatos.sort(key=lambda c: -c["nota"])
    escolhidos = []
    for c in candidatos:
        if all(abs(c["pico"] - e["pico"]) > 4 for e in escolhidos):
            escolhidos.append(c)
    if escolhidos:
        ref = np.median([c["nota"] for c in escolhidos])
        escolhidos = [c for c in escolhidos if c["nota"] >= ref * 1.5] or escolhidos[:1]
    return escolhidos[:8]


def folha_de_contato(caminho_saida, quadros, t, notas_sol, energia, saltos, colunas=8):
    passo = max(1, len(quadros) // 48)
    indices = list(range(0, len(quadros), passo))[:48]
    picos = {int(round(s["pico"] * AMOSTRAS_POR_SEG)) for s in saltos}
    miniaturas = []
    for i in indices:
        m = cv2.resize(quadros[i], (240, int(240 * quadros[i].shape[0] / quadros[i].shape[1])))
        m = cv2.copyMakeBorder(m, 0, 30, 0, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20))
        marca = "SALTO " if any(abs(i - p) <= passo for p in picos) else ""
        texto = f"{t[i]:.1f}s {marca}sol{notas_sol[i]:.2f} mov{energia[i]:.1f}"
        cv2.putText(m, texto, (4, m.shape[0] - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                    (0, 200, 255) if marca else (230, 230, 230), 1, cv2.LINE_AA)
        miniaturas.append(m)
    altura_max = max(m.shape[0] for m in miniaturas)
    miniaturas = [cv2.copyMakeBorder(m, 0, altura_max - m.shape[0], 0, 0, cv2.BORDER_CONSTANT) for m in miniaturas]
    while len(miniaturas) % colunas:
        miniaturas.append(np.zeros_like(miniaturas[0]))
    linhas = [np.hstack(miniaturas[i:i + colunas]) for i in range(0, len(miniaturas), colunas)]
    cv2.imwrite(str(caminho_saida), np.vstack(linhas), [cv2.IMWRITE_JPEG_QUALITY, 80])


def analisar(caminho):
    info = info_video(caminho)
    quadros = ler_quadros(caminho, info["duracao"])
    dt = 1 / AMOSTRAS_POR_SEG
    t = np.arange(len(quadros)) * dt
    sol = np.array([nota_por_do_sol(q) for q in quadros])
    energia, vy, camera = [0.0], [0.0], [0.0]
    for a, b in zip(quadros, quadros[1:]):
        e, v, c = sinais_movimento(a, b)
        energia.append(e)
        vy.append(v)
        camera.append(c)
    energia = suavizar(energia, 3)
    altura = suavizar(-np.cumsum(suavizar(vy, 3)), 3)
    # remove a deriva lenta para ficar só com subidas/descidas rápidas
    altura = altura - suavizar(altura, int(8 / dt))
    saltos = encontrar_saltos(t, altura, energia / (energia.mean() + 1e-6), dt)
    sol_suave = suavizar(sol, int(2 / dt))

    resultado = {
        "arquivo": caminho.name,
        **info,
        "saltos": saltos,
        "nota_por_do_sol": float(np.percentile(sol_suave, 90)) if len(sol_suave) else 0.0,
        "melhor_por_do_sol": float(t[int(np.argmax(sol_suave))]) if len(sol_suave) else 0.0,
        "sinais": {"t": t.round(2).tolist(), "sol": sol_suave.round(3).tolist(),
                   "energia": energia.round(3).tolist(), "altura": altura.round(2).tolist()},
    }
    PASTA_ANALISE.mkdir(exist_ok=True)
    (PASTA_ANALISE / f"{caminho.stem}.json").write_text(json.dumps(resultado, indent=1))
    folha_de_contato(PASTA_ANALISE / f"{caminho.stem}.jpg", quadros, t, sol_suave, energia, saltos)
    return resultado


def main():
    arquivos = sorted(p for p in PASTA_VIDEOS.rglob("*") if p.suffix.lower() in EXTENSOES)
    if not arquivos:
        sys.exit("Nenhum vídeo encontrado em videos/")
    for caminho in arquivos:
        r = analisar(caminho)
        picos = ", ".join(f"{s['pico']:.1f}s" for s in r["saltos"]) or "nenhum"
        print(f"{caminho.name}: {r['duracao']:.0f}s @ {r['fps']:.0f}fps | saltos: {picos} | "
              f"pôr do sol: {r['nota_por_do_sol']:.2f} (melhor em {r['melhor_por_do_sol']:.1f}s)")


if __name__ == "__main__":
    main()
