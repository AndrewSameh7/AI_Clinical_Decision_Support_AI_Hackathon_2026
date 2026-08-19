# Clinical Scope — Adult Hypertension - Day 1

## 1. Scope statement

This system is an educational clinical RAG prototype for answering questions about **adult hypertension** using two selected NICE documents: the NICE guideline **NG136, Hypertension in adults: diagnosis and management**, and the associated NICE patient decision aid **How do I control my blood pressure? Lifestyle options and choice of medicines**.

The system is not intended to diagnose an individual patient, prescribe treatment, provide patient-specific emergency advice, or replace qualified clinical judgement.

## 2. Target population

The primary clinical population is adults aged 18 years and over with raised blood pressure or hypertension, as covered by NG136. The guideline explicitly covers adults aged 18 and over, including people with type 2 diabetes.

## 3. In-scope clinical topics

The knowledge base is intentionally narrow and focuses on topics represented in the selected sources:

- Measuring blood pressure
- Diagnosing hypertension
- Ambulatory blood pressure monitoring (ABPM)
- Home blood pressure monitoring (HBPM)
- Cardiovascular risk assessment
- Assessment of target-organ damage
- Lifestyle interventions
- Starting antihypertensive drug treatment
- Monitoring treatment and blood-pressure targets
- Choosing antihypertensive treatment
- Same-day specialist review for severe hypertension
- Patient-oriented information about lifestyle and medication choices
- Medication advantages/disadvantages and side effects as covered by the patient decision aid
- Blood-test/monitoring information as covered by the selected sources

## 4. Explicitly out of scope

The system must not be represented as a general medical assistant. The following are outside the Day-1 scope:

- Diseases unrelated to adult hypertension
- Pregnancy-specific hypertension management
- Detailed management of chronic kidney disease, heart failure, diabetes, or other comorbidities when the answer requires those separate NICE guidelines
- Patient-specific diagnosis or treatment decisions
- Individual medication prescribing
- Emergency triage beyond accurately retrieving the relevant NG136 guidance
- Information not supported by the two indexed source documents
- General web knowledge or model-memory answers when the selected documents do not contain supporting evidence

Important: NG136 cross-references other NICE guidelines for situations such as pregnancy, chronic kidney disease, type 1 diabetes and heart failure. Those cross-referenced guidelines are not part of this Day-1 corpus. The RAG should therefore avoid implying that it has complete coverage of those topics.

## 5. Source roles

### NG136

Primary clinician-oriented source. It provides the core guideline recommendations for measurement, diagnosis, cardiovascular risk, target-organ damage, treatment, monitoring and same-day specialist review.

### Patient Decision Aid

Complementary patient-oriented source. It supports questions about lifestyle options, medication choices, advantages/disadvantages, side effects and related decision-support information.

## 6. Clinical validation principle

A retrieved chunk is considered clinically useful only when it preserves enough context to interpret the recommendation correctly. In particular, recommendation conditions, exceptions, thresholds and follow-up instructions should not be separated from the recommendation they qualify.

## 7. Evaluation scope

The Day-1 evaluation set covers:

1. ABPM diagnosis
2. HBPM diagnosis
3. Target-organ-damage investigations
4. Lifestyle interventions
5. ACE-inhibitor side effects
6. Blood-test/monitoring information around ACE inhibitor or ARB treatment
7. Antihypertensive medication options
8. Severe hypertension / 180/120 mmHg or higher

Each test question has an expected source/topic and should be evaluated against retrieved document, section and page metadata.

## 8. Safety boundary

The system is educational only. A retrieved recommendation must be treated as evidence from NICE, not as an individualized clinical order. The final system should include the project's clinical-safety disclaimer and should say when evidence cannot be found in the indexed documents.

## 9. Scope approval status

**Status: PENDING MENTOR APPROVAL**

Do not mark this scope as approved until the mentor has reviewed the selected documents, scope and legal/AI-reuse status.
