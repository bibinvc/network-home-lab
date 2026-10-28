# Verification — 28 October 2026

The lab was run on Ubuntu 24.04.3 LTS under WSL2, kernel 6.6.87.2-microsoft-standard-WSL2. Networking tools came from official Ubuntu packages, unpacked locally rather than installed as host services. See `evidence/environment.txt` for versions.

## Completed

- Created six separate network namespaces and four VLANs on a VLAN-filtering bridge.
- Created an 802.1Q trunk and four router subinterfaces.
- Acquired real DHCP leases for the client and guest; checked the advertised gateway and DNS option.
- Queried private DNS from both endpoints and checked the returned file-service address.
- Verified permitted client/admin requests before testing denied requests.
- Checked guest isolation, management access restrictions and blocked service-initiated connections.
- Confirmed that the router has no route to the Internet, without sending an external probe.
- Injected a VLAN 30 tag from the guest access port and confirmed it could not reach the VLAN 30 gateway.
- Recorded the test transcript: **17 passed, 0 failed**.
- Reproduced a client access-port shutdown, observed the DOWN link and incomplete neighbour entry, restored the port and verified the original service again.
- Captured lab traffic on the switch trunk. No host/Wi-Fi/home-network interface was captured.

The test source is `scripts/verify.sh`; the fault drill is `scripts/fault-drill.sh`. Timing/packet counters are observations from that run, not performance benchmarks.

## Scope

This verifies a virtual IPv4 lab on the environment above. It does not verify physical switching, vendor firmware, wireless networking, high availability, Internet/NAT access, IPv6 policy or production security. There is one endpoint per VLAN. The HTTP targets contain only synthetic lab text. No enterprise deployment or work history is implied.
