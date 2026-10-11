# chainedbox /boot.scr: boot an Armbian USB stick if present, else fall back to eMMC.
# U-Boot runs this before /boot/extlinux/extlinux.conf (prefix "/" is scanned before "/boot/").
# The stick's boot.scr imports armbianEnv.txt, which overwrites fdtfile and the load
# addresses, so they are saved here and restored if the stick boot returns.
setenv shim_devtype ${devtype}
setenv shim_devnum ${devnum}
setenv shim_prefix ${prefix}
setenv shim_bootpart ${distro_bootpart}
setenv shim_fdtfile ${fdtfile}
setenv shim_kaddr ${kernel_addr_r}
setenv shim_raddr ${ramdisk_addr_r}
echo "shim: scanning USB for an Armbian stick"
usb start
for d in 0 1 2 3 4; do
  if test -e usb ${d}:1 /armbianEnv.txt && test -e usb ${d}:1 /boot.scr; then
    echo "shim: Armbian stick at usb ${d}:1, chain-loading its boot.scr"
    setenv devtype usb
    setenv devnum ${d}:1
    setenv distro_bootpart 1
    setenv prefix /
    if load usb ${d}:1 0x00600000 /boot.scr; then source 0x00600000; fi
    echo "shim: stick boot returned, restoring eMMC settings"
    setenv devtype ${shim_devtype}
    setenv devnum ${shim_devnum}
    setenv prefix ${shim_prefix}
    setenv distro_bootpart ${shim_bootpart}
    setenv fdtfile ${shim_fdtfile}
    setenv kernel_addr_r ${shim_kaddr}
    setenv ramdisk_addr_r ${shim_raddr}
  fi
done
echo "shim: no stick booted, continuing with eMMC"
