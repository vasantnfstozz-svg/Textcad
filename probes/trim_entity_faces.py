"""Probe: can one sketch entity be more than one face? (trim takes faces()[0])"""
import sketch as sk

cases = {
  "bow-tie polygon (unequal lobes)": {"kind": "polygon", "mode": "add", "points":
      [[0,0],[10,0],[0,6],[10,6]]},
  "plain rect": {"kind": "rectangle", "mode": "add", "x":0,"y":0,"w":10,"h":5},
  "circle": {"kind": "circle", "mode":"add","x":0,"y":0,"r":5},
}
for name, e in cases.items():
    try:
        s = sk._entity(e)
        fs = s.faces()
        print(f"  {name:34s} faces={len(fs)}  total_area={sum(f.area for f in fs):.4f}"
              f"  face0={fs[0].area:.4f}")
    except Exception as ex:
        print(f"  {name:34s} RAISED {type(ex).__name__}: {ex}")
