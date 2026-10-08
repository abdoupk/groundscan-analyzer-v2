# Coding standards

Read during review, not implementation. The review agent imposes these;
the implementation agent optimizes for exploration and velocity.

## Every test names its failing input

For each new or touched test, state one concrete input that would make it
fail. A test with no failing input proves nothing. Shapes that failed
this bar before, and what each owed:

- An early return on the empty case (`if not x: return`) with the assertion
  after it: owes executing the populated path per distinct value, not
  truthiness of the condition.
- A copy-then-compare (`_replace` one field, assert another unchanged):
  owes a registry witness showing the two fields vary independently, so
  the comparison can actually disagree.
- Set equality between two live reads of the same source: owes proving
  the wiring, not the values — full-set parametrize marks plus one
  synthetic member the suite never saw.
- A substring grep standing in for a semantic property: owes the
  forbidden-vocabulary list the property actually excludes, checked
  against the fields that carry the justification.

Where the failing input cannot be constructed, say so in the test name
or a comment, and assert the weaker property honestly rather than
dressing it as the stronger one.
