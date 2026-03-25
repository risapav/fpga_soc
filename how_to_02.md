board/generators/
  gen_config.py          # orchestrátor (tenký)
  models.py              # dataclasses + Enum
  loader.py              # ConfigLoader + SchemaValidator
  builder.py             # ModelBuilder
  generators/
    rtl.py               # RTLGenerator (Jinja2)
    sw.py                # SWGenerator
    tcl.py               # TCLGenerator
  templates/
    soc_top.sv.j2
    soc_top_standalone.sv.j2
    reg_block.sv.j2
    soc_map.h.j2
    soc_map.md.j2
    sections.lds.j2
    files.tcl.j2
    generated_config.tcl.j2
    soc_interfaces.sv.j2

board/generators/
  gen_config.py     ~80 riadkov  (orchestrátor)
  models.py         ~110 riadkov (dataclasses + Enum)
  loader.py         ~90 riadkov  (ConfigLoader + SchemaValidator)
  builder.py        ~160 riadkov (ModelBuilder)
  generators/
    base.py         ~30 riadkov  (Jinja2 helper)
    rtl.py          ~60 riadkov  (RTLGenerator)
    sw.py           ~80 riadkov  (SWGenerator)
    tcl.py          ~40 riadkov  (TCLGenerator)
  templates/        8 x .j2 súborov

