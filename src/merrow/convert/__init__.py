"""Converters from publisher formats to Mermaid icon packs and styles, by format name."""

from merrow.convert import pdf, pptx, svg, visio
from merrow.model import Converter

CONVERTERS: dict[str, Converter] = {
    "svg": svg.build,
    "pdf": pdf.build,
    "pptx": pptx.build,
    "vssx": visio.build,
}
