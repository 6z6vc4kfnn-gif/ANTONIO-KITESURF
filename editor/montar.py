"""Monta o vídeo de kitesurf a partir da análise.

Fluxo:
  1. Lê analise/*.json (gerado por analisar.py) e monta um roteiro:
     abertura no pôr do sol -> navegação -> saltos em câmera lenta (o melhor por último)
     -> encerramento no pôr do sol.
  2. Se existir roteiro.json na raiz, ele é usado no lugar do automático
     (é assim que os cortes são ajustados à mão).
  3. Renderiza cada trecho com cor tratada, junta com transições, põe títulos e música.

Uso:
  python editor/montar.py                   # gera horizontal (16:9) e vertical (9:16)
  python editor/montar.py --so-roteiro      # só escreve analise/roteiro_auto.json
  python editor/montar.py --formato vertical
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

from analisar import EXTENSOES, PASTA_ANALISE, PASTA_VIDEOS, RAIZ

PASTA_SAIDA = RAIZ / "saida"
PASTA_MUSICA = RAIZ / "musica"
TEMP = RAIZ / ".trechos"
FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTE_FINA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FPS = 30
TRANSICAO = 0.5
FORMATOS = {"horizontal": (1920, 1080), "vertical": (1080, 1920)}

# Transição usada ao ENTRAR em cada tipo de trecho
TRANSICOES = {"abertura": "fade", "navegacao": "smoothleft", "salto": "smoothup",
              "climax": "fadewhite", "por_do_sol": "fade", "encerramento": "fadeblack"}


# ---------------------------------------------------------------- roteiro

def carregar_analises():
    analises = []
    for p in sorted(PASTA_ANALISE.glob("*.json")):
        if p.name.startswith("roteiro"):
            continue
        a = json.loads(p.read_text())
        if (PASTA_VIDEOS / a["arquivo"]).exists() or list(PASTA_VIDEOS.rglob(a["arquivo"])):
            analises.append(a)
    return analises


def caminho_video(nome):
    direto = PASTA_VIDEOS / nome
    return direto if direto.exists() else next(PASTA_VIDEOS.rglob(nome))


def livre(ocupado, arquivo, ini, fim):
    return all(not (ini < f and fim > i) for (a, i, f) in ocupado if a == arquivo)


def melhor_janela(a, chave, dur, ocupado, minimo=0.0):
    """Janela de `dur` segundos com maior média do sinal `chave`, sem sobrepor trechos já usados."""
    t, s = a["sinais"]["t"], a["sinais"][chave]
    if not t or a["duracao"] < dur + 0.5:
        return None
    passo = t[1] - t[0] if len(t) > 1 else 1 / 6
    n = max(1, int(dur / passo))
    melhor = None
    for i in range(0, len(t) - n, max(1, n // 4)):
        ini, fim = t[i], t[i] + dur
        if fim > a["duracao"] - 0.2 or not livre(ocupado, a["arquivo"], ini, fim):
            continue
        nota = sum(s[i:i + n]) / n
        if nota >= minimo and (melhor is None or nota > melhor[0]):
            melhor = (nota, ini, fim)
    return melhor


def roteiro_automatico(analises, duracao_alvo):
    ocupado, plano = [], []

    def usar(a, ini, fim, tipo, **extra):
        ocupado.append((a["arquivo"], ini, fim))
        plano.append({"arquivo": a["arquivo"], "inicio": round(ini, 2), "fim": round(fim, 2),
                      "tipo": tipo, **extra})

    # Saltos: nota do salto, com bônus se acontecer com o sol se pondo ao fundo
    saltos = []
    for a in analises:
        t, sol = a["sinais"]["t"], a["sinais"]["sol"]
        for s in a["saltos"]:
            idx = min(range(len(t)), key=lambda k: abs(t[k] - s["pico"])) if t else 0
            bonus = 1 + 3 * (sol[idx] if sol else 0)
            saltos.append((s["nota"] * bonus, a, s["pico"]))
    saltos.sort(key=lambda x: -x[0])
    max_saltos = max(1, int(duracao_alvo * 0.6 / 7))

    escolhidos = []
    for nota, a, pico in saltos:
        ini, fim = max(0, pico - 2.5), min(a["duracao"] - 0.1, pico + 2.5)
        if fim - ini < 2.5 or not livre(ocupado, a["arquivo"], ini - 1, fim + 1):
            continue
        ocupado.append((a["arquivo"], ini, fim))
        escolhidos.append((nota, a, pico, ini, fim))
        if len(escolhidos) >= max_saltos:
            break
    ocupado.clear()
    for _, a, _, ini, fim in escolhidos:
        ocupado.append((a["arquivo"], ini, fim))

    # Pôr do sol: arquivos com céu quente
    com_sol = sorted([a for a in analises if a["nota_por_do_sol"] > 0.05],
                     key=lambda a: -a["nota_por_do_sol"])
    abertura = encerramento = None
    for a in com_sol:
        j = melhor_janela(a, "sol", 5.5, ocupado)
        if j:
            abertura = (a, j)
            ocupado.append((a["arquivo"], j[1], j[2]))
            break
    for a in com_sol:
        j = melhor_janela(a, "sol", 6.0, ocupado)
        if j:
            encerramento = (a, j)
            ocupado.append((a["arquivo"], j[1], j[2]))
            break

    # Navegação: trechos com mais movimento, de arquivos variados
    tempo_saltos = sum(fim - ini + 2.5 for *_, ini, fim in escolhidos)
    n_navegacao = max(2, int((duracao_alvo - tempo_saltos - 12) / 3.2))
    navegacao = []
    rodada = 0
    while len(navegacao) < n_navegacao and rodada < 6:
        achou = False
        for a in sorted(analises, key=lambda a: -max(a["sinais"]["energia"] or [0])):
            j = melhor_janela(a, "energia", 3.2, ocupado)
            if j:
                ocupado.append((a["arquivo"], j[1], j[2]))
                navegacao.append((a, j))
                achou = True
            if len(navegacao) >= n_navegacao:
                break
        rodada += 1
        if not achou:
            break

    # Se não houver pôr do sol, abre e fecha com navegação
    if abertura:
        usar(abertura[0], abertura[1][1], abertura[1][2], "abertura")
    elif navegacao:
        a, j = navegacao.pop(0)
        usar(a, j[1], j[2], "abertura")

    climax = escolhidos[0] if escolhidos else None
    demais = list(reversed(escolhidos[1:]))  # do mais fraco ao mais forte
    for k in range(2):
        if navegacao:
            a, j = navegacao.pop(0)
            usar(a, j[1], j[2], "navegacao")
    for k, (_, a, pico, ini, fim) in enumerate(demais):
        usar(a, ini, fim, "salto", lento_de=round(pico - 1.2, 2), lento_ate=round(pico + 1.3, 2))
        if k % 2 == 1 and navegacao:
            a2, j = navegacao.pop(0)
            usar(a2, j[1], j[2], "navegacao")
    while navegacao:
        a, j = navegacao.pop(0)
        usar(a, j[1], j[2], "navegacao")
    if climax:
        _, a, pico, ini, fim = climax
        usar(a, ini, fim, "climax", lento_de=round(pico - 1.4, 2), lento_ate=round(pico + 1.5, 2))
    if encerramento:
        usar(encerramento[0], encerramento[1][1], encerramento[1][2], "encerramento")
    elif plano:
        plano[-1]["tipo"] = plano[-1]["tipo"] if plano[-1]["tipo"] == "climax" else "encerramento"
    for p in plano:
        p["inicio"] = max(0.0, p["inicio"])
    return plano


# ---------------------------------------------------------------- renderização

def correcao_de_cor(tipo):
    base = "eq=contrast=1.08:saturation=1.22:gamma=0.98"
    if tipo in ("abertura", "encerramento", "por_do_sol"):
        quente = "colorbalance=rs=0.06:gs=0.01:bs=-0.07:rm=0.05:bm=-0.05:rh=0.03:bh=-0.03"
    else:
        quente = "colorbalance=rm=0.02:bm=0.02:bs=0.03"  # mar mais azul, pele um pouco quente
    return f"{base},{quente},vignette=PI/5"


def renderizar_trecho(trecho, indice, largura, altura, tem_audio, fps_origem, suave):
    origem = caminho_video(trecho["arquivo"])
    ini, fim = float(trecho["inicio"]), float(trecho["fim"])
    dur = fim - ini
    lento = "lento_de" in trecho
    saida = TEMP / f"{largura}x{altura}_{indice:03d}.mp4"

    partes_v, partes_a, filtros = [], [], []
    if lento:
        a = max(0.0, float(trecho["lento_de"]) - ini)
        b = min(dur, float(trecho["lento_ate"]) - ini)
        cortes = [(0, a, 1.0), (a, b, 0.5), (b, dur, 1.0)]
    else:
        cortes = [(0, dur, 1.0)]
    cortes = [c for c in cortes if c[1] - c[0] > 0.05]
    n = len(cortes)
    filtros.append(f"[0:v]fps={max(FPS, round(fps_origem))},split={n}" + "".join(f"[vs{k}]" for k in range(n)))
    if tem_audio:
        filtros.append(f"[0:a]aresample=48000,asplit={n}" + "".join(f"[as{k}]" for k in range(n)))
    for k, (x, y, vel) in enumerate(cortes):
        cadeia = f"[vs{k}]trim={x:.3f}:{y:.3f},setpts=PTS-STARTPTS"
        if vel != 1.0:
            cadeia += f",setpts=PTS/{vel}"
            if suave and fps_origem < 50:
                cadeia += f",minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
        cadeia += f",fps={FPS}[v{k}]"
        filtros.append(cadeia)
        partes_v.append(f"[v{k}]")
        if tem_audio:
            cadeia_a = f"[as{k}]atrim={x:.3f}:{y:.3f},asetpts=PTS-STARTPTS"
            if vel != 1.0:
                cadeia_a += f",atempo={vel},volume=0.6"
            filtros.append(cadeia_a + f"[a{k}]")
        else:
            filtros.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{(y - x) / vel:.3f}[a{k}]")
        partes_a.append(f"[a{k}]")
    juntar = "".join(v + a for v, a in zip(partes_v, partes_a))
    filtros.append(f"{juntar}concat=n={n}:v=1:a=1[vj][aj]")
    # Enquadramento: preenche com o próprio vídeo desfocado ao fundo (vídeos em pé ou deitados)
    filtros.append(
        f"[vj]split[f][b];"
        f"[b]scale={largura // 4}:{altura // 4}:force_original_aspect_ratio=increase,"
        f"crop={largura // 4}:{altura // 4},boxblur=12:2,scale={largura}:{altura},eq=brightness=-0.08[fundo];"
        f"[f]scale={largura}:{altura}:force_original_aspect_ratio=decrease:flags=lanczos[frente];"
        f"[fundo][frente]overlay=(W-w)/2:(H-h)/2,{correcao_de_cor(trecho['tipo'])},"
        f"setsar=1,format=yuv420p[vout]")
    filtros.append("[aj]aformat=sample_rates=48000:channel_layouts=stereo[aout]")

    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.3f}", "-t", f"{dur:.3f}", "-i", str(origem),
           "-filter_complex", ";".join(filtros), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "aac", "-b:a", "192k",
           str(saida)]
    subprocess.run(cmd, check=True)
    return saida


def duracao(caminho):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(caminho)],
        capture_output=True, text=True, check=True).stdout.strip())


def texto(t, tamanho, y, ini, fim, fonte=FONTE, espacamento=0):
    t = t.replace("\\", "\\\\").replace("'", "’").replace(":", "\\:")
    alpha = (f"if(lt(t,{ini}),0,if(lt(t,{ini + 0.8}),(t-{ini})/0.8,"
             f"if(lt(t,{fim - 0.8}),1,if(lt(t,{fim}),({fim}-t)/0.8,0))))")
    return (f"drawtext=fontfile={fonte}:text='{t}':fontsize={tamanho}:fontcolor=white:"
            f"shadowcolor=black@0.55:shadowx=3:shadowy=3:x=(w-text_w)/2:y={y}:"
            f"alpha='{alpha}':enable='between(t,{ini},{fim})'")


def montar(plano, formato, args):
    largura, altura = FORMATOS[formato]
    infos = {}
    trechos = []
    for i, t in enumerate(plano):
        if t["arquivo"] not in infos:
            from analisar import info_video
            infos[t["arquivo"]] = info_video(caminho_video(t["arquivo"]))
        inf = infos[t["arquivo"]]
        print(f"  [{formato}] trecho {i + 1}/{len(plano)}: {t['tipo']} {t['arquivo']} "
              f"{t['inicio']:.1f}-{t['fim']:.1f}s")
        trechos.append(renderizar_trecho(t, i, largura, altura, inf["tem_audio"], inf["fps"], args.suave))

    duracoes = [duracao(p) for p in trechos]
    entradas, filtros = [], []
    for p in trechos:
        entradas += ["-i", str(p)]
    rotulo_v, rotulo_a = "[0:v]", "[0:a]"
    acumulado = duracoes[0]
    for k in range(1, len(trechos)):
        trans = TRANSICOES.get(plano[k]["tipo"], "fade")
        offset = acumulado - TRANSICAO
        filtros.append(f"{rotulo_v}[{k}:v]xfade=transition={trans}:duration={TRANSICAO}:offset={offset:.3f}[xv{k}]")
        filtros.append(f"{rotulo_a}[{k}:a]acrossfade=d={TRANSICAO}[xa{k}]")
        rotulo_v, rotulo_a = f"[xv{k}]", f"[xa{k}]"
        acumulado += duracoes[k] - TRANSICAO
    total = acumulado

    # Títulos
    escala = largura / 1920 if formato == "horizontal" else 1.0
    y_titulo = "(h-text_h)/2-40" if formato == "horizontal" else "h*0.40"
    camadas = [texto(args.titulo, int(150 * escala), y_titulo, 0.6, 4.8, espacamento=20)]
    if args.subtitulo:
        camadas.append(texto(args.subtitulo, int(54 * escala), y_titulo.replace("-40", "+110") if formato == "horizontal"
                             else "h*0.40+190", 1.2, 4.8, FONTE_FINA))
    if args.final:
        camadas.append(texto(args.final, int(70 * escala), "(h-text_h)/2" if formato == "horizontal" else "h*0.45",
                             max(0, total - 4.5), total - 0.3, FONTE_FINA))
    fade_final = f"fade=t=out:st={total - 1.2:.3f}:d=1.2"
    filtros.append(f"{rotulo_v}{','.join(camadas)},{fade_final},format=yuv420p[vfinal]")

    musicas = sorted(p for p in PASTA_MUSICA.glob("*") if p.suffix.lower() in {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}) \
        if PASTA_MUSICA.exists() else []
    if musicas:
        entradas += ["-stream_loop", "-1", "-i", str(musicas[0])]
        m = len(trechos)
        filtros.append(f"{rotulo_a}volume={args.volume_original}[orig]")
        filtros.append(f"[{m}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
                       f"afade=t=in:d=1.0,afade=t=out:st={total - 3:.3f}:d=3[mus]")
        filtros.append("[mus][orig]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[afinal]")
    else:
        filtros.append(f"{rotulo_a}loudnorm=I=-16:TP=-1.5,afade=t=out:st={total - 1.5:.3f}:d=1.5[afinal]")

    PASTA_SAIDA.mkdir(exist_ok=True)
    destino = PASTA_SAIDA / f"kitesurf_{formato}.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", *entradas, "-filter_complex", ";".join(filtros),
           "-map", "[vfinal]", "-map", "[afinal]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destino)]
    subprocess.run(cmd, check=True)
    print(f"  -> {destino.relative_to(RAIZ)} ({total:.1f}s)")
    return destino


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--formato", choices=["horizontal", "vertical", "ambos"], default="ambos")
    ap.add_argument("--duracao", type=float, default=75, help="duração alvo em segundos")
    ap.add_argument("--titulo", default="KITESURF")
    ap.add_argument("--subtitulo", default="")
    ap.add_argument("--final", default="")
    ap.add_argument("--volume-original", type=float, default=0.18,
                    help="volume do som original quando há música")
    ap.add_argument("--suave", action="store_true",
                    help="câmera lenta com interpolação de quadros (mais lento de renderizar)")
    ap.add_argument("--so-roteiro", action="store_true")
    args = ap.parse_args()

    manual = RAIZ / "roteiro.json"
    if manual.exists():
        plano = json.loads(manual.read_text())
        print(f"Usando roteiro manual ({len(plano)} trechos)")
    else:
        analises = carregar_analises()
        if not analises:
            raise SystemExit("Rode antes: python editor/analisar.py")
        plano = roteiro_automatico(analises, args.duracao)
        (PASTA_ANALISE / "roteiro_auto.json").write_text(json.dumps(plano, indent=1, ensure_ascii=False))
        print(f"Roteiro automático: {len(plano)} trechos -> analise/roteiro_auto.json")
    if args.so_roteiro:
        return

    TEMP.mkdir(exist_ok=True)
    formatos = ["horizontal", "vertical"] if args.formato == "ambos" else [args.formato]
    for f in formatos:
        montar(plano, f, args)
    shutil.rmtree(TEMP, ignore_errors=True)


if __name__ == "__main__":
    main()
