# Ollama Cloud model probe (2026-10-29)

`python -m downshift.probe --provider ollama --all --workers 3` sent six tiny requests to every model the
`https://ollama.com/v1/models` endpoint lists for this account: a tool-calling prompt (default settings and
with `reasoning_effort: none`), a plain question (default, `none`, `low`) and a `response_format: json_schema`
request. `out` = completion tokens, `rN` = characters of returned reasoning, `tc` = tool called. All 23
models, three in flight at a time, finished in about three minutes; the Pro subscription made it free.

## Raw table

| model | tools, default | tools, reasoning_effort=none | plain, default | plain, none | plain, low | json_schema |
|---|---|---|---|---|---|---|
| beam | out=55 r146 tc=get_weather tool_calls 1.5s | out=38 r69 tc=get_weather tool_calls 1.1s | out=126 r440 tc=- stop 2.5s | out=131 r482 tc=- stop 2.5s | out=107 r397 tc=- stop 1.9s | out=70 stop '{"city":"Paris","country":"France"}' |
| clef:27b | ERR 400 (not a chat model) | ERR 400 | ERR 400 | ERR 400 | ERR 400 | ERR 400 |
| deepseek-v4-pro:0813 | out=67 r90 tc=get_weather tool_calls 1.0s | out=53 tc=get_weather tool_calls 0.7s | out=59 r215 tc=- stop 0.7s | out=24 tc=- stop 0.6s | out=62 r204 tc=- stop 0.8s | out=38 stop '{"city": "Paris", "country": "France"}' |
| deepseek-v4.1-flash | out=52 r50 tc=get_weather tool_calls 0.6s | out=39 tc=get_weather tool_calls 0.5s | out=65 r236 tc=- stop 0.6s | out=25 tc=- stop 0.5s | out=70 r260 tc=- stop 0.8s | out=45 stop '{"city":"Paris","country":"France"}' |
| deepseek-v4.1-flash:1017 | out=40 tc=get_weather tool_calls 0.5s | out=39 tc=get_weather tool_calls 0.5s | out=80 r257 tc=- stop 0.8s | out=40 tc=- stop 0.5s | out=63 r229 tc=- stop 3.1s | out=34 stop '{"city":"Paris","country":"France"}' |
| gemma4:31b | out=15 tc=get_weather tool_calls 0.4s | out=15 tc=get_weather tool_calls 0.4s | out=22 tc=- stop 0.5s | out=27 tc=- stop 0.5s | out=299 r1208 tc=- stop 1.9s | out=25 stop '```json {   "city": "Paris",   "country"' |
| glm-5.2 | out=38 r113 tc=get_weather tool_calls 0.7s | out=11 tc=get_weather tool_calls 0.7s | out=385 r1505 tc=- stop 1.6s | out=27 tc=- stop 0.6s | out=392 r1560 tc=- stop 1.9s | out=131 stop '```json {   "city": "Paris",   "country"' |
| glm-5.3 | out=35 r102 tc=get_weather tool_calls 0.8s | out=32 tc=get_weather tool_calls 7.4s | out=181 r743 tc=- stop 14.5s | out=183 tc=- stop 1.3s | out=33 tc=- stop 6.2s | out=100 stop '```json {   "city": "Paris",   "country"' |
| glm-5.3-flash | out=34 r98 tc=get_weather tool_calls 1.2s | out=39 tc=get_weather tool_calls 1.3s | out=96 r306 tc=- stop 1.7s | out=168 tc=- stop 2.2s | out=22 tc=- stop 0.9s | out=51 stop '```json {   "city": "Paris",   "country"' |
| gpt-oss:120b | out=47 r87 tc=get_weather tool_calls 0.6s | out=60 r129 tc=get_weather tool_calls 0.6s | out=73 r184 tc=- stop 0.7s | out=84 r256 tc=- stop 0.6s | out=43 r27 tc=- stop 0.6s | out=77 stop '```json {   "city": "Paris",   "country"' |
| gpt-oss:20b | out=37 r52 tc=get_weather tool_calls 0.8s | out=37 r66 tc=get_weather tool_calls 1.0s | out=147 r566 tc=- stop 1.6s | out=172 r682 tc=- stop 2.0s | out=40 r36 tc=- stop 0.9s | out=82 stop '{"city":"Paris","country":"France"}' |
| kimi-k2.6 | out=50 r151 tc=get_weather tool_calls 1.8s | out=17 tc=get_weather tool_calls 1.6s | out=183 r883 tc=- stop 7.5s | out=21 tc=- stop 0.9s | out=195 r906 tc=- stop 6.2s | out=91 stop '```json {   "city": "Paris",   "country"' |
| kimi-k2.7-code | out=51 r150 tc=get_weather tool_calls 0.9s | out=18 tc=get_weather tool_calls 0.7s | out=208 r924 tc=- stop 2.4s | out=20 tc=- stop 0.8s | out=81 r317 tc=- stop 1.3s | out=79 stop '```json {   "city": "Paris",   "country"' |
| kimi-k3 | out=67 r78 tc=get_weather tool_calls 1.4s | out=54 tc=get_weather tool_calls 1.8s | out=396 r1731 tc=- stop 4.4s | out=49 tc=- stop 1.4s | out=51 r30 tc=- stop 1.4s | out=80 stop '```json {   "city": "Paris",   "country"' |
| minimax-m2.7 | out=55 r125 tc=get_weather tool_calls 1.6s | out=62 r151 tc=get_weather tool_calls 1.5s | out=187 r819 tc=- stop 6.1s | out=249 r1137 tc=- stop 6.9s | out=170 r732 tc=- stop 4.5s | out=110 stop '  ```json {   "city": "Paris",   "countr' |
| minimax-m3 | out=62 r147 tc=get_weather tool_calls 4.5s | out=28 tc=get_weather tool_calls 2.7s | out=80 r340 tc=- stop 2.6s | out=20 tc=- stop 1.6s | out=87 r377 tc=- stop 1.6s | out=18 stop '{   "city": "Paris",   "country": "Franc' |
| minimax-m3.1-flash | out=39 tc=get_weather tool_calls 3.0s | out=35 tc=get_weather tool_calls 1.7s | out=61 r227 tc=- stop 1.3s | out=21 tc=- stop 1.1s | out=29 r34 tc=- stop 1.0s | out=40 stop '{"city":"Paris","country":"France"}' |
| mistral-large-3:675b | out=12 tc=get_weather tool_calls 1.8s | out=12 tc=get_weather tool_calls 0.9s | out=24 tc=- stop 1.1s | out=24 tc=- stop 1.1s | out=24 tc=- stop 1.5s | out=40 stop 'Here is the capital of France in JSON fo' |
| mistral-large-4 | out=58 r202 tc=get_weather tool_calls 1.8s | ERR 500 Internal | out=600 r3005 tc=- length 3.8s | ERR 500 Internal | out=286 r1235 tc=- stop 2.3s | out=151 stop '```json {   "city": "Paris",   "country"' |
| muse-spark-open | out=99 r216 tc=get_weather tool_calls 1.3s | out=76 tc=get_weather tool_calls 1.2s | out=523 r2466 tc=- stop 4.3s | out=225 tc=- stop 2.3s | out=247 r1099 tc=- stop 5.1s | out=66 stop '{"city": "Paris", "country": "France"}' |
| nemotron-3-nano:30b | out=150 r588 tc=get_weather tool_calls 0.9s | out=25 tc=get_weather tool_calls 0.6s | out=110 r426 tc=- stop 0.8s | out=18 tc=- stop 0.5s | out=108 r425 tc=- stop 0.8s | out=66 stop '{   "city": "Paris",   "country": "Franc' |
| nemotron-3-super | out=41 r64 tc=get_weather tool_calls 1.0s | out=25 tc=get_weather tool_calls 0.5s | out=89 r266 tc=- stop 1.1s | out=32 tc=- stop 0.5s | out=50 r64 tc=- stop 1.6s | out=61 stop '{   "city": "Paris",   "country": "Franc' |
| nemotron-3-ultra | out=58 r149 tc=get_weather tool_calls 26.5s | out=25 tc=get_weather tool_calls 2.6s | out=52 r73 tc=- stop 2.1s | out=28 tc=- stop 0.9s | out=118 r363 tc=- stop 6.1s | out=178 stop '{   "city": "Paris",   "country": "Franc' |

## What it means

| model | tool calls | thinks by default | `reasoning_effort: none` switches thinking off | `low` | strict JSON from json_schema | note |
|---|---|---|---|---|---|---|
| nemotron-3-nano/super/ultra | yes | yes | yes (reasoning chars 0, tokens drop 4-6×) | still thinks (Nano: same length as default) | yes | `low` is not a smaller budget on this route: Nano r425 vs r426 |
| deepseek-v4-pro, deepseek-v4.1-flash (both tags) | yes | yes | yes | no change | yes | cleanest controls of the non-NVIDIA models |
| glm-5.2, glm-5.3, glm-5.3-flash | yes | yes | yes | glm-5.3 and 5.3-flash: thinking off at `low` too | no (```json fence) | |
| kimi-k2.6, kimi-k2.7-code, kimi-k3 | yes | yes | yes | kimi-k3: shorter (r30) | no (fence) | |
| minimax-m3, minimax-m3.1-flash | yes | yes | yes | m3.1-flash shorter (r34) | yes | |
| minimax-m2.7 | yes | yes | **no** (r151 / r1137) | no | no (fence) | thinking cannot be switched off this way |
| gpt-oss:20b, gpt-oss:120b | yes | yes | **no** (`none` ignored) | yes, shorter (r36 / r27) | 20b yes, 120b fence | "off" must map to `reasoning_effort: low` for this family |
| gemma4:31b | yes | **no** | n/a | **turns thinking on** (r1208) | no (fence) | a non-thinking model with an opt-in thinking mode |
| mistral-large-3:675b | yes | no | n/a | n/a | **no** (prose) | no reasoning at all; ignores json_schema |
| mistral-large-4 | yes | yes | **500 error** | shorter | no (fence) | hit the 600-token cap while thinking; `none` crashes the route |
| muse-spark-open | yes | yes | yes | shorter | yes | identity unknown at probe time; see the catalog report |
| beam | yes | yes | **no** | no | yes | identity unknown at probe time; see the catalog report |
| clef:27b | — | — | — | — | — | 400 on every chat request: not a chat model |

Consequences for Downshift:

1. **The reasoning switch is per model, not per provider.** `models.yaml` maps `reasoning: off` to one
   request field per provider; gpt-oss, minimax-m2.7, gemma4 and beam break that assumption. Model entries
   need an optional `reasoning:` override (gpt-oss: off → `reasoning_effort: low`; gemma4: on → `low`;
   minimax-m2.7 and beam: off unsupported, so the optimizer must not be offered it).
2. **`low|medium|high` are not budgets on Nemotron here.** Nano returned the same reasoning length at `low`
   as by default. Until a provider is verified to honour them, the harness schema should expose only
   on/off for Nemotron, so the optimizer cannot pick a no-op.
3. **Structured outputs are not enforced** for most models on this route (fenced ```json instead of bare
   JSON; Mistral Large 3 answered in prose). Anything that parses model JSON must strip fences; the
   optimizer should not be told json_schema is a reliable fix.
4. **Everything that matters is fast**: sub-2 s per call for most models, so an optimization round on
   these models is minutes, not hours; the binding limit is the concurrency cap (3 in flight).
5. **Exclude** clef:27b (not chat), mistral-large-4 (route errors on `none`, long default thinking) and,
   pending identification, beam.
