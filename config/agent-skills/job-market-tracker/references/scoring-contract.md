# Scoring contract

The agent scores evidence; the script sums components, applies caps, chooses priority, and preserves manual overrides.

Return one object per pending job inside a batch wrapper. Copy `run_id` exactly from the pending payload:

```json
{
  "run_id": "run-0123456789ab",
  "scores": [
    {
      "job_id": "job-0123456789ab",
      "lane": "applied-ml-operations",
      "components": {
        "role_fit": 22,
        "technical_alignment": 21,
        "delivery_ownership": 17,
        "domain_alignment": 13,
        "logistics": 12
      },
      "matches": ["Production time-series ML", "End-to-end technical ownership"],
      "gaps": ["No stated optimisation work"],
      "uncertainties": ["Salary not published"],
      "summary": "Senior applied-ML ownership for connected industrial assets.",
      "critical_unknown": false,
      "hard_blocker": false,
      "hard_blocker_reason": null
    }
  ]
}
```

## Lanes

- `applied-ml-operations`: primary lane; senior hands-on ML for operational decisions, time series, sensors, forecasting, optimisation, or production data products.
- `computer-vision-edge`: secondary lane; real-world vision, video, multimodal evidence, edge constraints, or physical systems.
- `applied-ai-systems`: selective lane; production LLM/VLM integration with evaluation, governance, human review, and operational ownership.
- `other`: use when the title matched a search but the work does not fit these lanes.

## Components

### Role fit — 0 to 25

Reward senior individual-contributor scope, hands-on modelling, applied research-to-production work, and an operational problem. Penalise primarily people-management, generic analytics, pure platform engineering, or junior scope.

### Technical alignment — 0 to 25

Reward Python, SQL, AWS/cloud, PySpark/large data, production ML, time series, anomaly detection, optimisation, computer vision, PyTorch, sensor/IoT data, evaluation, or relevant deployment. Score evidence, not keyword count.

### Delivery and ownership — 0 to 20

Reward end-to-end ownership, ambiguous problem framing, deployment, measurement, stakeholder adoption, customer work, production reliability, and communication across disciplines.

### Domain alignment — 0 to 15

Reward industrial IoT, energy, climate, infrastructure, food tech, manufacturing, logistics, aviation, mobility, fleet, supply chain, or an applied-AI consultancy delivering real operational systems.

### Logistics — 0 to 15

Use the listing only. Full score for UK remote. Strong score for hybrid reachable from Rushden in about 90 minutes, including London via Wellingborough, with no more than two expected office days weekly. Reduce for unclear frequency or materially longer travel. Use 0 and a hard blocker for a role that requires residence/work outside the UK or incompatible full-time onsite attendance. Salary unknown is neutral.

## Deterministic priorities

- A: total at least 85, logistics at least 12, full description available, posted or refreshed within 14 days, and no critical unknown or hard blocker.
- B: total 72–84, or an otherwise A-level role capped by age, incomplete logistics, or a material unknown.
- C: total 55–71.
- Excluded: below 55 or any hard blocker.

An incomplete description cannot receive A. Do not inflate scores to compensate for missing evidence. `critical_unknown` is for something that could change an A-level recommendation, such as unknown mandatory office frequency; routine unpublished salary belongs only in `uncertainties`.
