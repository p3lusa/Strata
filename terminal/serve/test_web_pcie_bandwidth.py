"""The Monitor tab's PCIe card on a GPU that reports no byte counters (consumer AMD: amdgpu exposes no
traffic counters and amdsmi_get_gpu_pci_throughput answers NOT_SUPPORTED, #7106 rule): the card shows the
bandwidth the engine measured instead — pcie_mb_s per request and the sampler's per-second series — and a
card that does report gpu_pcie_rx_mb (Nvidia, Intel) keeps the old rendering. Runs app.js's own
pcieBandwidth() under node.

    python -m unittest serve/test_web_pcie_bandwidth.py
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
NODE = shutil.which("node")


def function_source(text: str, name: str) -> str:
    start = text.index(f"function {name}(")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


@unittest.skipUnless(NODE, "node is needed to run the page's own code")
class PcieBandwidthCard(unittest.TestCase):
    def bandwidth(self, hw, h, requests):
        src = function_source((WEB / "app.js").read_text(encoding="utf-8"), "pcieBandwidth")
        out = subprocess.run(
            [NODE, "-e",
             f"{src}\nprocess.stdout.write(JSON.stringify("
             f"pcieBandwidth({json.dumps(hw)}, {json.dumps(h)}, {json.dumps(requests)})));"],
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=True)
        return json.loads(out.stdout)

    def test_a_card_that_counts_bytes_keeps_the_old_rendering(self):
        # an Nvidia card reports gpu_pcie_rx_mb; the derived path must not touch it
        self.assertIsNone(self.bandwidth({"gpu_pcie_rx_mb": 1234.0}, {"pcie_mb_s": [1.0, 2.0]},
                                         [{"pcie_mb_s": 999.0}]))

    def test_a_card_without_counters_shows_the_engine_measured_bandwidth(self):
        # the 9070 XT: no rx counter, but the server publishes pcie_mb_s per request and per second
        got = self.bandwidth({"gpu_pcie_rx_mb": None},
                             {"pcie_mb_s": [0.0, 0.0, 4700.0, 1988.3, 0.0]},
                             [{"pcie_mb_s": 1988.3}, {"pcie_mb_s": 4700.0}])
        self.assertEqual(got["mb"], 4700.0)
        self.assertEqual(got["series"], [0.0, 0.0, 4700.0, 1988.3, 0.0])

    def test_a_server_from_before_the_derived_fields_stays_empty(self):
        # an old server has neither the per-request field nor the series: the card renders as before
        self.assertIsNone(self.bandwidth({"gpu_pcie_rx_mb": None}, {"gpu_util": [1.0, 2.0]},
                                         [{"pcie_share": 0.2}]))

    def test_idle_still_draws_the_series(self):
        # after a restart the series is all zeros and no request ran yet: the sparkline still has data
        got = self.bandwidth({"gpu_pcie_rx_mb": None}, {"pcie_mb_s": [0.0, 0.0, 0.0]}, [])
        self.assertIsNone(got["mb"])
        self.assertEqual(got["series"], [0.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
