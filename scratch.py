from pysnmp.entity.engine import SnmpEngine
eng = SnmpEngine()
print("mibViewController in cache?", "mibViewController" in eng.cache)
