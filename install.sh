#!/usr/bin/env bash
# ==============================================================================
#  FLAC Audiophile Player — Otomatik Kurulum ve Bağımlılık Yükleyici
#  Desteklenen Dağıtımlar: Arch Linux / CachyOS, Fedora, Ubuntu / Debian
# ==============================================================================

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RESET="\033[0m"

echo -e "${CYAN}${BOLD}◆ FLAC Audiophile Player Kurulum Sihirbazı ◆${RESET}\n"

# 1. Dağıtım Tespiti
PKG_MANAGER=""
INSTALL_CMD=""

if command -v pacman &>/dev/null; then
    PKG_MANAGER="Arch / CachyOS (pacman)"
    INSTALL_CMD="sudo pacman -S --needed --noconfirm"
    PKGS=("cava" "mpv" "chafa" "ffmpeg" "python-numpy" "python-pillow")
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="Fedora (dnf)"
    INSTALL_CMD="sudo dnf install -y"
    PKGS=("cava" "mpv" "chafa" "ffmpeg" "python3-numpy" "python3-pillow")
elif command -v apt-get &>/dev/null; then
    PKG_MANAGER="Debian / Ubuntu (apt)"
    INSTALL_CMD="sudo apt-get install -y"
    PKGS=("cava" "mpv" "chafa" "ffmpeg" "python3-numpy" "python3-pil")
else
    echo -e "${YELLOW}Desteklenen paket yöneticisi otomatik bulunamadı.${RESET}"
    echo "Lütfen şu paketleri manuel kurun: cava, mpv, chafa, ffmpeg, python-numpy, python-pillow"
    exit 1
fi

echo -e "Tespit edilen sistem: ${GREEN}${PKG_MANAGER}${RESET}"
echo -e "Kurulacak paketler: ${BOLD}${PKGS[*]}${RESET}\n"

# Kullanıcı onayı (Terminal etkileşimli ise)
if [ -t 0 ]; then
    read -rp "Bağımlılıklar yüklensin mi? [E/h]: " confirm
    if [[ "$confirm" =~ ^[hHnN]$ ]]; then
        echo -e "${YELLOW}Kurulum iptal edildi.${RESET}"
        exit 0
    fi
fi

# Kurulumu başlat
echo -e "\n${CYAN}Paketler kuruluyor...${RESET}"
$INSTALL_CMD "${PKGS[@]}"

# İzinleri düzenle
chmod +x run.sh main.py import_autoeq.py 2>/dev/null || true

echo -e "\n${GREEN}${BOLD}✓ Tüm bağımlılıklar başarıyla kuruldu!${RESET}"
echo -e "CAVA görselleştirici ve Chafa kapak motoru aktif edildi."
echo -e "\nBaşlatmak için: ${BOLD}./run.sh${RESET}\n"
