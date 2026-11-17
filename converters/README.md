# converters

The converters live in [src/merrow/convert/](../src/merrow/convert/), one per source format (`svg`, `pptx`, `vssx`), all reading their options from config. They never alter the artwork, never recolour it and never rescale it.

[prototypes/](prototypes/) holds the first working versions, with paths hard-coded to the machine they were written on. Visio page conversion and the AWS post-render step are still only there.
