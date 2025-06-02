# QEMU-Mininet Integration pentru Testare de Rețea

Acest proiect oferă o integrare între QEMU și Mininet pentru testarea și simularea topologiilor de rețea complexe. Proiectul permite rularea mașinilor virtuale QEMU în cadrul unei topologii Mininet, oferind o platformă flexibilă pentru testarea scenariilor de rețea.

## Componente Principale

### 1. QemuHost (`qemu_mininet_components.py`)
- Clasa principală pentru gestionarea mașinilor virtuale QEMU în Mininet
- Caracteristici:
  - Gestionare automată a imaginilor QEMU (overlay)
  - Configurare automată a interfețelor TAP
  - Suport pentru SSH și execuție de comenzi în VM
  - Gestionare IP și rutare
  - Suport pentru VLAN-uri

### 2. QemuSwitch (`qemu_mininet_components.py`)
- Implementare de switch bazat pe Open vSwitch
- Suport pentru:
  - Configurare VLAN
  - Trunk ports
  - Access ports

### 3. LinuxRouter (`qemu_mininet_components.py`)
- Router Linux pentru gestionarea traficului între rețele
- Suport pentru:
  - Rutare statică
  - Interfețe VLAN
  - IP forwarding

### 4. QemuCLI (`qemu_cli.py`)
- CLI personalizat pentru interacțiunea cu nodurile QEMU
- Permite execuția de comenzi direct în VM-uri

### 5. Experiment Runner (`main_experiment_runner.py`)
- Script principal pentru rularea experimentelor
- Funcționalități:
  - Încărcare dinamică a topologiilor
  - Configurare automată a rețelei
  - Gestionare VLAN
  - Configurare hosts și rutare

## Cerințe de Sistem

- Linux (testat pe Ubuntu 20.04+)
- Python 3.6+
- QEMU
- Open vSwitch
- Mininet
- sshpass (pentru automatizarea SSH)

## Instalare

1. Instalați dependențele sistem:
```bash
sudo apt-get update
sudo apt-get install -y qemu-system-x86 ovs-vsctl mininet sshpass
```

2. Creați imaginea QEMU de bază:
```bash
# Creați o imagine QEMU de bază și salvați-o în locația specificată în BASE_QEMU_IMAGE
qemu-img create -f qcow2 /path/to/qemu_image.qcow2 10G
```

3. Configurați imaginea QEMU:
- Instalați un sistem de operare Linux în imagine
- Configurați SSH
- Setați parola root la '0944' (sau modificați în cod)

## Configurare

1. Modificați `BASE_QEMU_IMAGE` în `qemu_mininet_components.py` pentru a indica calea către imaginea QEMU de bază.

2. Asigurați-vă că Open vSwitch rulează:
```bash
sudo service openvswitch-switch start
```

## Rulare Experimente

1. Creați o topologie personalizată în directorul `topologies/`

2. Rulați experimentul:
```bash
sudo python3 main_experiment_runner.py --topo YourTopology
```

## Topologii Implementate

Proiectul include mai multe topologii predefinite pentru diferite scenarii de testare:

### 1. Basic LAN (`topology_basic_lan.py`)
- Topologie simplă cu două mașini virtuale conectate printr-un switch
- Rețea: 10.0.0.0/24
- Hosturi:
  - q1: 10.0.0.10/24
  - q2: 10.0.0.11/24
- Ideal pentru testarea comunicării de bază între VM-uri

### 2. VLAN (`topology_vlan.py`)
- Topologie cu suport pentru VLAN-uri
- Structură:
  - Switch s1 cu porturi trunk și access
  - Router r0 cu interfețe VLAN
  - Două VLAN-uri (100 și 200)
- Rețele:
  - VLAN 100: 10.0.100.0/24
  - VLAN 200: 10.0.200.0/24
- Hosturi per VLAN:
  - VLAN 100: q1, q2
  - VLAN 200: q3, q4
- Suport pentru rutare între VLAN-uri

### 3. Multi-Router (`topology_multi_router.py`)
- Topologie complexă cu două LAN-uri interconectate prin routere
- Structură:
  - LAN 1: q1, q2 -- s1 -- r0
  - LAN 2: q3, q4 -- s2 -- r1
  - Conexiune: r0 -- r1
- Rețele:
  - LAN 1: 10.0.1.0/24
  - LAN 2: 10.0.3.0/24
  - Interconectare: 10.0.12.0/30
- Rutare statică între rețele

### 4. Scaled LAN (`topology_scaled_lan.py`)
- Topologie pentru testarea performanței cu mai multe VM-uri
- Suport pentru configurare dinamică a numărului de hosturi
- Ideal pentru testarea scalabilității

### 5. Routed Subnets (`topology_routed_subnets.py`)
- Topologie cu subrețele separate prin routere
- Suport pentru rutare între subrețele diferite
- Configurare flexibilă a rutelor

Pentru a utiliza o topologie specifică, specificați numele clasei topologiei la rulare:
```bash
sudo python3 main_experiment_runner.py --topo BasicLanTopo
sudo python3 main_experiment_runner.py --topo VlanTopo
sudo python3 main_experiment_runner.py --topo MultiRouterTopo
```

## Probleme Comune și Soluții

### 1. Erori la pornirea QEMU
- Verificați dacă imaginea QEMU există și este accesibilă
- Asigurați-vă că porturile SSH nu sunt deja în uz
- Verificați permisiunile pentru fișierele QEMU

### 2. Probleme de conectivitate
- Verificați configurația IP în topologie
- Asigurați-vă că rutarea este configurată corect
- Verificați firewall-ul în VM-uri

### 3. Probleme cu VLAN-uri
- Verificați configurația OVS
- Asigurați-vă că interfețele TAP sunt adăugate corect la bridge
- Verificați configurația sub-interfețelor pe router

## Structura Proiectului

```
qemu_mininet/
├── qemu_mininet_components.py  # Componente principale
├── qemu_cli.py                 # CLI personalizat
├── main_experiment_runner.py   # Runner principal
└── topologies/                 # Topologii personalizate
```

## Contribuții

Pentru a contribui la proiect:
1. Fork repository-ul
2. Creați un branch pentru feature-ul dvs.
3. Commit și push
4. Creați un Pull Request

## Licență

Acest proiect este licențiat sub [MIT License](LICENSE).

## Contact

Pentru întrebări și suport, vă rugăm să deschideți un issue în repository. 