#!/bin/bash
# Native arm64 Linux build (Lima VM / container), gcc 9: no x86 toolchains needed.
# usage (inside the VM): build-local.sh /path/to/tb-x606v-kernel
set -e
REPO=$1; W=${W:-$HOME/kbuild}; mkdir -p $W; cd $W
sudo apt-get update -qq
sudo apt-get install -y -qq git make gcc bc bison flex libssl-dev device-tree-compiler python2 xz-utils \
  gcc-arm-linux-gnueabihf kmod cpio libelf-dev
[ -d src ] || git clone --depth 1 https://github.com/UsrBinLuna/kernel_lenovo_achilles6.git src
cd src
git checkout -q . 
for p in $REPO/patches/*.patch; do git apply --check "$p" 2>/dev/null && git apply "$p" && echo "applied $p" || echo "SKIPPED $p"; done
sed -i 's/^subdir-ccflags-y += -Werror/#&/' arch/arm64/Makefile   # gcc 9 flags warnings the vendor code never saw
printf '#!/bin/sh\nexec gcc -fcommon "$@"\n' > $W/hostgcc; chmod +x $W/hostgcc
# gcc 9 is newer than this tree expects: silence the warnings that arch/arm64/Makefile turns into errors
W9="-Wno-packed-not-aligned -Wno-address-of-packed-member -Wno-stringop-truncation -Wno-stringop-overflow -Wno-array-bounds -Wno-maybe-uninitialized -Wno-format-overflow -Wno-format-truncation -Wno-restrict -Wno-sizeof-pointer-memaccess -Wno-misleading-indentation -Wno-int-in-bool-context -Wno-attribute-alias -Wno-cast-function-type -Wno-missing-attributes -Wno-multistatement-macros"
M=(ARCH=arm64 O=out CROSS_COMPILE= CROSS_COMPILE_ARM32=arm-linux-gnueabihf- python=python2 HOSTCC=$W/hostgcc "KCFLAGS=$W9")
make "${M[@]}" achilles6_row_call_defconfig
./scripts/kconfig/merge_config.sh -m -O out out/.config $REPO/config/android16.fragment
make "${M[@]}" olddefconfig
make "${M[@]}" -k -j8 Image.gz-dtb > $W/build.log 2>&1 || { grep -E "error:|\*\*\*|undefined reference" $W/build.log | head -40; exit 1; }
ls -l out/arch/arm64/boot/Image.gz-dtb
