# Troubleshooting notes

## Client loses access to the file service

The fault drill shuts down `p-client` inside the virtual switch. The client keeps its DHCP address, but requests time out because its access link is down.

Order of checks:

1. `ip -n bvc-hl-client -br address` — is the expected lease still present?
2. `ip -br -n bvc-hl-switch link show p-client` — is the access port UP?
3. `ip netns exec bvc-hl-switch bridge vlan show` — is the client port an untagged member of VLAN 30?
4. `ip -n bvc-hl-client route` — is the gateway `10.77.30.1`?
5. `ip -n bvc-hl-client neigh show` — can the gateway's MAC address be resolved?
6. Check DNS separately, then try the file service by IP. This avoids treating a DNS fault as a routing fault.
7. Inspect the router's firewall counters before changing policy.

Recovery:

```bash
sudo ./lab.sh client-port-up
sudo ip netns exec bvc-hl-client curl --noproxy '*' http://10.77.20.10:8080
```

The recorded drill has a successful request before the shutdown, a timeout while the port is down, the observed link/neighbor state and a successful request after restoration. The script restores the port on exit, including after a failed check.

## Guest requests time out

That is expected for inter-VLAN requests. First confirm the guest received `10.77.40.100`, its gateway is reachable and DNS returns `10.77.20.10`. Then compare the permitted client request with the denied guest request and inspect the `Guest isolation` counter. Do not add a broad allow rule just to make ping succeed.

## DHCP does not finish

Check `run/dhcp-client.log` or `run/dhcp-guest.log`, then `run/dnsmasq.log`. Verify the access-port PVID, the tagged VLAN on the trunk and the router subinterface address. The MAC addresses and reservations are fixed in this lab. No host DHCP service is involved.

## Starting twice or cleaning up

An existing namespace is a reason to stop and inspect, not to delete every namespace on the machine. Use `./lab.sh down` from the same repository directory that created the lab. If the directory has been moved, the ownership check intentionally refuses cleanup. Never substitute `ip -all netns delete` or a host `nft flush ruleset` command.
