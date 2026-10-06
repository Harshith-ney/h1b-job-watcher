from collectors.amazon import AmazonCollector
from collectors.apple import AppleCollector
from collectors.ashby import AshbyCollector
from collectors.eightfold import EightfoldCollector
from collectors.google import GoogleCollector
from collectors.greenhouse import GreenhouseCollector
from collectors.jibe import JibeCollector
from collectors.lever import LeverCollector
from collectors.oracle import OracleCollector
from collectors.workday import WorkdayCollector

REGISTRY = {
    "amazon": AmazonCollector,
    "apple": AppleCollector,
    "ashby": AshbyCollector,
    "eightfold": EightfoldCollector,
    "google": GoogleCollector,
    "greenhouse": GreenhouseCollector,
    "jibe": JibeCollector,
    "lever": LeverCollector,
    "oracle": OracleCollector,
    "workday": WorkdayCollector,
}


def build(cfg: dict, http):
    try:
        cls = REGISTRY[cfg["collector"]]
    except KeyError:
        raise ValueError(f"unknown collector '{cfg['collector']}' for {cfg['key']}") from None
    return cls(cfg, http)
