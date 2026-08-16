# Evaluation Report

Config: LLM provider = `mock`, embedding backend = `tfidf`

- **Retrieval accuracy**: 90% (9/10 tickets)
- **Mean groundedness** (generated drafts only): 94%
- **Gate distribution**: {'AUTO_SUGGEST': 7, 'NEEDS_REVIEW': 1, 'ESCALATE_LOW_GROUNDEDNESS': 0, 'ESCALATE_NO_KB_MATCH': 2}
- **Secret redaction check** (ticket 1006 never leaks the pasted token): PASS
- **Out-of-scope escalation check** (ticket 1007 escalates instead of hallucinating): PASS

| Ticket | Expected KB | Retrieved KB | Hit | Gate | Groundedness |
|---|---|---|---|---|---|
| 1001 Can't log in - not receiving password re | kb_001 | kb_001, kb_008, kb_006 | ✅ | AUTO_SUGGEST | 1.0 |
| 1002 SAML signature invalid error after IdP c | kb_002 | kb_002, kb_005, kb_010 | ✅ | AUTO_SUGGEST | 1.0 |
| 1003 Why was I charged for 5 extra seats this | kb_003 | kb_003, kb_010, kb_009 | ✅ | AUTO_SUGGEST | 1.0 |
| 1004 Getting 429 errors when syncing 2000 tas | kb_004 | kb_004, kb_006, kb_009 | ✅ | AUTO_SUGGEST | 1.0 |
| 1005 Webhook not receiving any events | kb_005 | kb_005, kb_009, kb_002 | ✅ | NEEDS_REVIEW | 0.5 |
| 1006 Here is my API token, please check my ac | kb_010 | kb_004, kb_001, kb_010 | ✅ | ESCALATE_NO_KB_MATCH | - |
| 1007 Does Northwind Cloud support integrating | (none) | kb_002, kb_010, kb_004 | ✅ | ESCALATE_NO_KB_MATCH | - |
| 1008 Can a Member role edit tasks in a projec | kb_007 | kb_007, kb_006, kb_009 | ✅ | AUTO_SUGGEST | 1.0 |
| 1009 Someone logged into our workspace from a | kb_010 | kb_001, kb_006, kb_007 | ❌ | AUTO_SUGGEST | 1.0 |
| 1010 How do I stop getting so many email noti | kb_008 | kb_008, kb_006, kb_001 | ✅ | AUTO_SUGGEST | 1.0 |