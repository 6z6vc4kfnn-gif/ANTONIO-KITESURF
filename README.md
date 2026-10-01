# Kitesurf: editor de vídeo

Monta um vídeo de kitesurf a partir dos vídeos brutos, priorizando saltos/manobras (em câmera lenta) e o pôr do sol.

## Como usar

```bash
pip install opencv-python-headless numpy      # precisa também do ffmpeg
# 1. coloque os vídeos em videos/
python3 editor/analisar.py                     # acha saltos, pôr do sol e movimento; gera folhas de contato em analise/
# 2. (opcional) ajuste os cortes em roteiro.json; sem ele, o roteiro é automático
python3 editor/trilha.py --duracao 36.6 --acao 3.8 --climax 23.6 --sol 27.5   # trilha sincronizada
python3 editor/montar.py --suave --volume-original 0.12 --final "vento • mar • pôr do sol"
```

Saída: `saida/kitesurf_vertical.mp4` (1080x1920, Reels/Stories/TikTok) e `saida/kitesurf_horizontal.mp4` (1920x1080, YouTube).

Para usar uma música própria, coloque o arquivo (.mp3/.m4a/.wav) em `musica/` no lugar de `trilha.wav`.

## roteiro.json

Cada trecho: `arquivo`, `inicio`, `fim` (segundos), `tipo` (`abertura`, `navegacao`, `salto`, `climax`, `por_do_sol`, `encerramento`) e, opcionalmente, `lento_de`/`lento_ate` para câmera lenta (0,5x). O tipo define a correção de cor (quente no pôr do sol) e a transição.
