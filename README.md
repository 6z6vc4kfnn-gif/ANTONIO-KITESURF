# Kitesurf: editor de vídeo

Monta um vídeo de kitesurf a partir dos vídeos brutos, priorizando saltos/manobras (em câmera lenta) e o pôr do sol.

## Como usar

```bash
pip install opencv-python-headless numpy      # precisa também do ffmpeg
# 1. coloque os vídeos em videos/
python3 editor/analisar.py                     # acha saltos, pôr do sol e movimento; gera folhas de contato em analise/
# 2. (opcional) ajuste os cortes em roteiro.json; sem ele, o roteiro é automático
python3 editor/trilha.py --duracao 36.6 --acao 3.8 --climax 23.6 --sol 27.5   # trilha sincronizada
python3 editor/montar.py --suave --volume-original 0.12
```

Saída: `saida/kitesurf_vertical.mp4` (1080x1920, Reels/Stories/TikTok) e `saida/kitesurf_horizontal.mp4` (1920x1080, YouTube).

Para usar uma música própria, coloque o arquivo (.mp3/.m4a/.wav) em `musica/` no lugar de `trilha.wav`.

## roteiro.json

Cada trecho: `arquivo`, `inicio`, `fim` (segundos), `tipo` (`abertura`, `navegacao`, `salto`, `climax`, `por_do_sol`, `encerramento`) e, opcionalmente, `lento_de`/`lento_ate` para câmera lenta (0,5x). O tipo define a correção de cor (quente no pôr do sol) e a transição.

## Fotos

Fotos (.jpg/.png) em `fotos/` podem entrar no roteiro com movimento lento:

```json
{"arquivo": "f02.jpg", "duracao": 3.0, "tipo": "foto", "movimento": "pan", "pan_de": 0.0, "pan_ate": 0.55}
{"arquivo": "f03.jpg", "duracao": 3.6, "tipo": "encerramento", "movimento": "zoom", "zoom": 0.07}
```

Cada trecho aceita também `transicao` (efeito do xfade) e `dur_transicao` (segundos) para sobrescrever o padrão do tipo.

## Reels da Barrinha de Baixo (1 minuto)

```bash
python3 editor/trilha.py --duracao 60.1 --acao 10.02 --climax 47.22 --sol 52.33 --bpm 100
python3 editor/montar.py --roteiro roteiro_barrinha.json --formato vertical --suave --volume-original 0.10 --manter-trechos
python3 editor/montar.py --roteiro roteiro_barrinha.json --formato vertical --suave --sem-musica --sufixo _sem_musica
```

Só vídeos, sem fotos. Cada salto aparece inteiro, da aproximação até depois do pouso. A câmera lenta (`lento_de`/`lento_ate`) começa na decolagem e termina no pouso; o resto do trecho roda em velocidade normal. Os cortes da ação caem na grade de 100 bpm.
