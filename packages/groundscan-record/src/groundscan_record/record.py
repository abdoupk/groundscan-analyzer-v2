"""One document rendered for review as self-contained HTML.

The reader is a colleague who has to accept or challenge a number. The
page leads with the headline and carries the doubt on the same page, not
one click away and not in a footnote. Findings and doubt go in;
machinery stays out: a field that explains what the engine did stays
out of the headline sections and appears only in the verbatim appendix,
while a field that lets the reader judge the finding is transcribed.

The record renders and does not measure: sorting, grouping and
labelling are presentation, and any figure the engine did not produce is
a ticket against the engine rather than a line this package adds. It
deliberately computes no readiness: no aggregate, no fitness, no
quality level and no confidence figure appears anywhere.

One template renders both document shapes. Whether a document is a
survey is answered by the data rather than by the caller: the four
survey-only sections appear only when their fields are non-empty.
Two runs over the same document bytes produce byte-identical files:
the render is a pure function of the document with no clock, no
randomness and no build step. Output is one HTML file with embedded
CSS, no external asset and no network reference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

from jinja2 import BaseLoader, Environment

from groundscan_analyzer import document as document_module

if TYPE_CHECKING:
    from pathlib import Path

RecordSection = Literal[
    "headline",
    "scan",
    "finding",
    "withholding",
    "open-question",
    "relation-note",
    "frame-note",
    "contradiction-note",
    "recurrence-note",
    "source",
]

RECORD_SECTIONS: Final[tuple[RecordSection, ...]] = (
    "headline",
    "scan",
    "finding",
    "withholding",
    "open-question",
    "relation-note",
    "frame-note",
    "contradiction-note",
    "recurrence-note",
    "source",
)

_CSS: Final[str] = (
    "body{font-family:system-ui,sans-serif;line-height:1.5;"
    "max-width:70rem;margin:2rem auto;padding:0 1rem;color:#111}"
    "header.record-headline{border-bottom:0.2rem solid #111;"
    "margin-bottom:2rem}"
    "section{margin-bottom:2rem}"
    ".record-finding{border:0.1rem solid #555;padding:1rem;"
    "margin-bottom:1rem}"
    ".record-withholding{background:#f4f4f4;padding:1rem}"
    ".record-open-question{background:#fff8e1;padding:1rem;"
    "border-left:0.4rem solid #b26a00}"
    "table{border-collapse:collapse;margin:0.5rem 0}"
    "th,td{border:0.05rem solid #999;padding:0.3rem 0.6rem;"
    "text-align:left}"
    "details{border:0.1rem solid #555;padding:1rem}"
    "pre{white-space:pre-wrap;word-break:break-word}"
)

TEMPLATE: Final[str] = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Field acceptance record</title>
<style>{{ css }}</style>
</head>
<body>
<header class="record-headline">
<h1>Field acceptance record</h1>
<p>One document rendered for review. Headline first,
doubt beside it.</p>
</header>
{% for scan in doc.scans %}
<section class="record-scan">
<h2>Scan at position {{ scan.position }}</h2>
<p>Engine status: {{ scan.status }}</p>
{% if scan.status == "read" %}
<p>Declared extent: {{ scan.extent.field_length }},
{{ scan.extent.field_width }}</p>
<p>Latitude presence: {{ scan.latitude_presence }}</p>
<p>Longitude presence: {{ scan.longitude_presence }}</p>
<p>Line order: {{ scan.line_order }}</p>
<p>Payload digest: {{ scan.payload_hash }}</p>
{% if scan.discrepancies %}
<h3>Observed facts</h3>
<ul>
{% for item in scan.discrepancies %}
<li>{{ item.kind }}: {{ item.detail }}</li>
{% endfor %}
</ul>
{% endif %}
<h3>Vendor echo cross-check</h3>
<p>Checked: {{ scan.metric_check.checked }}</p>
<p>Tolerance: {{ scan.metric_check.tolerance }}</p>
{% if scan.metric_check.mismatches %}
<ul>
{% for miss in scan.metric_check.mismatches %}
<li>{{ miss.axis }} at {{ miss.impulse }},{{ miss.scan_line }}:
wanted {{ miss.expected }}, saw {{ miss.observed }}</li>
{% endfor %}
</ul>
{% endif %}
{% if scan.aspect_checks %}
<h3>Aspect verdicts</h3>
<ul>
{% for check in scan.aspect_checks %}
<li>{{ check.first }} to {{ check.second }} {{ check.relation }}:
{{ check.verdict }} ({{ check.note }})</li>
{% endfor %}
</ul>
{% endif %}
<h3>Robust scale</h3>
<p>Status: {{ scan.robust_scale.status }}</p>
<p>Estimates: {{ scan.robust_scale.sigma_mad }},
{{ scan.robust_scale.sigma_iqr }}</p>
<p>Disagreement: {{ scan.robust_scale.disagreement }}</p>
<p>Derived tolerance:
{{ scan.robust_scale.tolerance }}</p>
<p>Atom fraction: {{ scan.robust_scale.median_atom_numerator }}
of {{ scan.robust_scale.median_atom_denominator }}</p>
<h3>Scale-normalised view</h3>
<p>Status: {{ scan.scale_normalised_view.status }}</p>
<p>Reason: {{ scan.scale_normalised_view.reason }}</p>
<p>Scale: {{ scan.scale_normalised_view.scale }}</p>
{% if scan.perturbation_bound %}
<p>Field bound: {{ scan.perturbation_bound.amplitude }}
{{ scan.perturbation_bound.anchor }}
{{ scan.perturbation_bound.boundedness }}</p>
{% else %}
<p>Field bound: no recorded bound</p>
{% endif %}
{% if scan.displacement_bound %}
<p>Displacement bound:
{{ scan.displacement_bound.amplitude }}
{{ scan.displacement_bound.boundedness }}</p>
{% else %}
<p>Displacement bound: no recorded bound</p>
{% endif %}
<h3>Mask guard</h3>
<p>Status: {{ scan.mask_invariance.status }}</p>
<p>Reason: {{ scan.mask_invariance.reason }}</p>
<p>Ordering: {{ scan.mask_invariance.ordering_invariance }}</p>
<p>Magnitude:
{{ scan.mask_invariance.magnitude_invariance }}</p>
<h3>Self-alignment evidence</h3>
<p>Status: {{ scan.registration.status }}</p>
<p>Reason: {{ scan.registration.reason }}</p>
<p>Margin: {{ scan.registration.margin }}</p>
<p>Correlation: {{ scan.registration.correlation }}</p>
<p>Argmax: {{ scan.registration.argmax_dy }},
{{ scan.registration.argmax_dx }}</p>
<p>Argmax stable: {{ scan.registration.argmax_stable }}</p>
<p>Margin drift: {{ scan.registration.margin_drift }}</p>
<p>Shift count: {{ scan.registration.shift_count }}</p>
<p>Assessed count: {{ scan.registration.scored_count }}</p>
{% if scan.registration.shifts %}
<ul>
{% for shift in scan.registration.shifts %}
<li>Shift {{ shift.dy }},{{ shift.dx }}:
{{ shift.correlation }} over {{ shift.overlap }}</li>
{% endfor %}
</ul>
{% endif %}
<h3>Hierarchy tallies</h3>
<p>Measured cells: {{ scan.hierarchy.measured_cells }}</p>
<p>Cells in hierarchy:
{{ scan.hierarchy.cells_in_hierarchy }}</p>
{% for tally in scan.hierarchy.detection_counts %}
<p>Detection tally {{ tally.polarity }}: {{ tally.count }}
over {{ tally.denominator }}</p>
{% endfor %}
{% for tally in scan.hierarchy.component_counts %}
<p>Component tally {{ tally.polarity }} at {{ tally.level }}:
{{ tally.count }} over {{ tally.denominator }}</p>
{% endfor %}
{% for finding in scan.hierarchy.detections %}
<section class="record-finding">
<h4>Finding {{ finding.number }}</h4>
<p>Identity: {{ finding.identity }}</p>
<p>Polarity: {{ finding.polarity }}</p>
<p>Birth level: {{ finding.birth_level }}</p>
<p>Cell count: {{ finding.cell_count }}</p>
<p>Solidity: {{ finding.solidity }}</p>
<p>Compactness: {{ finding.compactness }}</p>
{% if finding.field_area is not none %}
<p>Field area: {{ finding.field_area }}</p>
{% else %}
<p class="record-withholding">Field area withheld:
{{ finding.field_area_withheld }}</p>
{% endif %}
{% if finding.depth %}
<p>Depth interval: {{ finding.depth.minimum }}
to {{ finding.depth.maximum }}</p>
{% endif %}
<p>Scan-local: {{ finding.scan_local_position.along_line.index
}},
{{ finding.scan_local_position.across_lines.index }}</p>
{% if finding.field_position %}
<p>Field along: {{ finding.field_position.along_line.coordinate
}}</p>
<p>Field across:
{{ finding.field_position.across_lines.coordinate }}</p>
{% else %}
<p class="record-withholding">Field position withheld:
{{ finding.no_field_position_reason }}</p>
{% endif %}
{% if finding.shared_frame_position %}
<p>Shared frame: {{ finding.shared_frame_position.frame }}</p>
{% else %}
<p class="record-withholding">Shared position withheld:
{{ finding.no_shared_position_reason }}</p>
{% endif %}
{% if finding.limitations %}
<p>Limitations: {{ finding.limitations | join(", ") }}</p>
{% else %}
<p>Limitations: none stated</p>
{% endif %}
</section>
{% endfor %}
{% else %}
<p>Reason: {{ scan.reason }}</p>
<p>Detail: {{ scan.detail }}</p>
{% if scan.rows %}
<ul>
{% for row in scan.rows %}
<li>Line {{ row.line }}: {{ row.reason }}</li>
{% endfor %}
</ul>
{% endif %}
{% endif %}
</section>
{% endfor %}
{% if doc.declared_relations %}
<section class="record-relation-note">
<h2>Declared relations</h2>
<ul>
{% for rel in doc.declared_relations %}
<li>{{ rel.first }} to {{ rel.second }}: {{ rel.relation }}
({{ rel.source }})</li>
{% endfor %}
</ul>
</section>
{% endif %}
{% if doc.frames %}
<section class="record-frame-note">
<h2>Shared frames</h2>
{% for frame in doc.frames %}
<h3>{{ frame.label }}</h3>
<p>Name: {{ frame.name }}</p>
<p>Members: {{ frame.members | join(", ") }}</p>
{% if frame.limitations %}
<p>Limitations: {{ frame.limitations | join(", ") }}</p>
{% endif %}
{% endfor %}
</section>
{% endif %}
{% if doc.contradictions %}
<section class="record-contradiction-note">
<h2>Contradictions</h2>
<ul>
{% for item in doc.contradictions %}
<li>{{ item.first }} to {{ item.second }} {{ item.relation }}:
declared {{ item.declared_class }},
expected {{ item.expected_class }}</li>
{% endfor %}
</ul>
</section>
{% endif %}
{% if doc.recurrences %}
<section class="record-recurrence-note">
<h2>Recurrences</h2>
<ul>
{% for item in doc.recurrences %}
<li>{{ item.first }} with {{ item.second }}:
{{ item.eligibility }}, {{ item.reason }}, {{ item.status }}</li>
{% endfor %}
</ul>
</section>
{% endif %}
<section class="record-source">
<h2>Source</h2>
<p>Contract {{ doc.contract_version }},
registry {{ doc.registry_version }},
quantities {{ doc.quantity_registry_version }}</p>
<p>Digests:
{% for scan in doc.scans %}{% if scan.status == "read"
%}{{ scan.payload_hash }} {% endif %}{% endfor %}</p>
<details>
<summary>Source document (verbatim)</summary>
<pre>{{ doc_json }}</pre>
</details>
</section>
</body>
</html>
"""


def _environment() -> Environment:
    """Build the Jinja2 environment behind the single template.

    Returns:
        The environment with HTML autoescape and no loader,
        so the template is a string and there is no build step.
    """
    return Environment(loader=BaseLoader(), autoescape=True)


def render(doc: document_module.Document) -> str:
    """Render one document to one self-contained HTML string.

    The render is a pure function of the document: no clock, no
    randomness and no network, so two runs over the same document
    bytes produce byte-identical files. Sorting, grouping and
    labelling are presentation only; every number shown is
    transcribed from the document and no aggregate is computed.

    Args:
        doc: The validated survey document to render.

    Returns:
        The self-contained HTML with embedded CSS.
    """
    env = _environment()
    template = env.from_string(TEMPLATE)
    payload = document_module.dumps(doc)
    return template.render(doc=doc, doc_json=payload, css=_CSS)


def write_record(doc: document_module.Document, path: Path) -> Path:
    """Write one rendered document to one HTML file.

    Args:
        doc: The validated survey document to render.
        path: The destination file path.

    Returns:
        The destination path unchanged.
    """
    path.write_text(render(doc), encoding="utf-8")
    return path
