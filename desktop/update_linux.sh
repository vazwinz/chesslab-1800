#!/usr/bin/env bash
# Atualiza o AURA instalado neste Linux a partir deste clone: puxa o código novo do GitHub, gera o
# app e troca a versão instalada (a antiga só sai se o build der certo), depois reabre o AURA.
# Na pasta do projeto:
#   bash desktop/update_linux.sh        DRY_RUN=1 só mostra o que faria; NO_START=1 não reabre
# Os dados (~/.local/share/aura) não são tocados.
set -Eeuo pipefail
trap 'echo ">> Parou: algo falhou acima." >&2' ERR

main() {
  cd "$(dirname "$0")/.."
  local app="$HOME/.local/opt/aura"
  if [ "${DRY_RUN:-0}" = "1" ]; then
    git fetch -q
    echo ">> Código: $(git status -sb | head -n 1)"
    echo ">> Geraria o app (desktop/build_linux.sh, uns minutos) e trocaria $app"
    if pgrep -f "$app/" >/dev/null 2>&1; then echo ">> Fecharia o AURA aberto"; fi
    echo ">> Simulação: nada foi mudado."
    return
  fi
  git checkout -- frontend/tsconfig.tsbuildinfo 2>/dev/null || true  # o build mexe nele
  git pull --ff-only
  echo ">> Gerando o app novo e trocando a versão instalada (uns minutos)..."
  bash desktop/build_linux.sh
  git checkout -- frontend/tsconfig.tsbuildinfo 2>/dev/null || true
  echo ">> Fechando o AURA antigo, se estiver aberto..."
  pkill -f "$app/" 2>/dev/null || true
  sleep 2
  pkill -9 -f "$app/" 2>/dev/null || true
  echo ">> Pronto: AURA atualizado (commit $(git rev-parse --short HEAD))."
  if [ "${NO_START:-0}" != "1" ]; then nohup "$app/AURA" >/dev/null 2>&1 & fi
}

# o arquivo inteiro é lido antes de rodar: o git pull pode reescrever este próprio script
main "$@"
exit
