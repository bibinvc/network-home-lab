# Recorded evidence

Outputs in this directory are from the isolated lab. All addresses, MACs, DNS names and service payloads belong to the project. The capture is taken on the virtual trunk inside `bvc-hl-switch`; it is not a capture of the host, Wi-Fi or home LAN.

`connectivity.txt` records the 17 checks, including expected failures. `network-state.txt` records switch VLAN membership, router addresses/routes, firewall counters and DHCP leases. `fault-drill.txt` records access-port shutdown and recovery. `validation.pcap` contains the lab traffic; `packet-excerpt.txt` is a short decoded view.

The decoded excerpt uses UTC, like the test transcripts. Open the capture in Wireshark to inspect the 802.1Q tags, DHCP exchange, DNS answers and TCP traffic.
