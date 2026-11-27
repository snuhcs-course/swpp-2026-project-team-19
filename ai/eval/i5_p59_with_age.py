"""Run i3_match_eval.py with the line's age passed to the matcher, as menu import does (I5-P59).

    python ai/eval/i5_p59_with_age.py <i3_match_eval.py arguments>

The harness gives the matcher the line name only (ExtractedProduct(product_name=name)). Menu
import also passes the extracted age (`extracted_age_years`), which the alias rules compare with
the product's age (resolve._compare_attributes: ageConflict). Here the age is read from the line
name with the S2 age pattern (staged._AGE_WITH_UNIT: "12년", "12Y", "12yo"), as a stand-in for
what extraction would give. Measurement only; API 0 calls without --llm.
"""

import sys

import i3_match_eval as h


def main(argv=None) -> dict:
    original = h.Backend.resolve

    def resolve_with_age(self, name, catalog):
        staged = sys.modules["app.matching.staged"]
        match = staged._AGE_WITH_UNIT.search(name or "")
        age = int(match[1]) if match else None
        return self.resolve_staged(self.ExtractedProduct(product_name=name, age_years=age), catalog, h.STAGES)

    h.Backend.resolve = resolve_with_age
    try:
        return h.main(argv)
    finally:
        h.Backend.resolve = original


if __name__ == "__main__":
    main()
