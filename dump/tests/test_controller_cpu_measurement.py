import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"source"))
import controller

def test_cpu_admission_needs_two_samples_and_positive_elapsed_ticks(monkeypatch):
    samples=iter(["cpu 100 0 0 100 0 0 0 0 0 0\n","cpu 100 0 0 100 0 0 0 0 0 0\n","cpu 200 0 0 100 0 0 0 0 0 0\n","cpu 300 0 0 160 0 0 0 0 0 0\n"])
    original=Path.read_text
    def read_text(path,*args,**kwargs):
        return next(samples) if str(path)=="/proc/stat" else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"read_text",read_text)
    monkeypatch.setattr(controller.os,"cpu_count",lambda:16)
    monkeypatch.setattr(controller,"CPU_PREVIOUS",None)
    monkeypatch.setattr(controller,"LAST_IDLE_CORES",99.0)
    assert controller.cpu_idle_cores()==0.0
    assert controller.cpu_idle_cores()==0.0
    assert controller.cpu_idle_cores()==0.0
    assert controller.cpu_idle_cores()==6.0
