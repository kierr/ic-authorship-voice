# negative_llm scenario deck

Each row is a task a frontier model is asked to render as a UK-IC Key-Judgements
block. Scenario sources are deliberately NON-IC (press / court / FCA / FATF /
threat-report facts) so the model must transfer into the UK assessment register
without the register vocabulary baked in — this is where the natural failure
modes surface. Every output is labelled with its dominant failure_mode (§1).

## Scenarios

1. Press report: a UK payments firm processed £890m for a state-owned exporter
   without a money-transfer licence. Render the enforcement conclusion.
2. Court judgment summary: a London solicitor laundered £2.4m through a
   dormant property shell over 36 months. Render the assessment.
3. FCA notice: a bank's transaction-monitoring missed 11,000 alert-groups for 14
   months; audits found no corrective action. Render.
4. Policing: an organised crime group consolidating a county-lines drugs route
   after a rival's arrest; 3 new firearms emerged. Render.
5. FATF: a jurisdiction's CDD rules exempt remittance corridors, enabling
   layering; effectiveness is rated low. Render.
6. Cyber: a state-aligned group expanded into cloud data exfiltration, exploiting
   a misconfigured identity provider across four ministries. Render.
7. Elections: a foreign influence operation amplified fringe content toward a
   general election; platforms did little. Render.
8. Transport: a state-linked airline exceeded a sanctioned component threshold,
   routing dual-use parts through a third country. Render.
9. Energy: a fixed pipeline supplying a NATO ally became dependent on a hostile
   state's oil; 2 interconnectors failed. Render.
10. Migration: a smuggler network switched to faster boats and cut prices after
    an enforcement gap; numbers doubled in a quarter. Render.
11. Health: a hostile actor probed a vaccine cold-chain firm's SCADA; an
    incident was detected but the payload was cleared. Render.
12. Finance: a bank's correspondent relationships became a channel for Russian
    sanctions-evasion trade finance; senior sign-off was deficient. Render.
13. Threats: an actor acquired a chemical-precursor used only in agent class A
    nerve agents; provenance was unverified. Render.
14. IP: a research institute leaked 17 proposals in a month to a competitor
    state; an insider was the only plausible vector. Render.
15. Elections: malinformation mimicking a regulator's branding appeared in the
    run up to a home election; it spread to 30 constituencies. Render.
16. Enabling: a logistics firm's subsidiaries were used to move dual-use goods
    to an embargoed end-user; licence checks lapsed. Render.
17. Cyber-frauds: a business-email-compromise wave hit a sector tied to a
    government contract; losses reached a 5-year high. Render.
18. Counter-terrorism: a plotter acquired a vehicle and a knife; the threat was
    independently assessed as likely but the plot was diffuse. Render.
19. Migration: a state's agents facilitated irregular transit across a
    displacement corridor; a smuggling network consolidated. Render.
20. Organised crime: a theft ring moved into ephedrine importation with
    manufacturing intent; a lab was disrupted. Render.

Output schema per row (JSONL):
{"id": "nllm-<n>", "scenario": "<topic>", "class": "negative_llm",
 "output": "<the model's KJF block>", "failure_modes": ["...","..."],
 "dominant_failure": "<one of §7 taxonomy>"}