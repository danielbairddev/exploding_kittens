Pull the latest trained weights from the server, bump stats_version on any bot that got new weights, commit, and push. Auto-deploy handles the server restart.

Steps:
1. On the server, copy each bot's best weights into agents/ so they're ready to pull:
     ssh root@162.243.161.27 "cd /opt/ek-arena && cp training/rhino/best_policy.json agents/rhino_weights.json && cp training/gorilla/best_policy.json agents/orangutan2_weights.json && cp training/elephant/best_policy.json agents/elephant_weights.json 2>/dev/null; echo done"
2. SCP those files locally:
     scp root@162.243.161.27:/opt/ek-arena/agents/rhino_weights.json agents/rhino_weights.json
     scp root@162.243.161.27:/opt/ek-arena/agents/orangutan2_weights.json agents/orangutan2_weights.json
     scp root@162.243.161.27:/opt/ek-arena/agents/elephant_weights.json agents/elephant_weights.json  (skip if missing)
3. For each weights file that actually changed (check git diff), bump the stats_version integer in the corresponding agent file:
   - rhino_weights.json      → agents/rhino_agent.py
   - orangutan2_weights.json → agents/orangutan2_agent.py
   - elephant_weights.json   → agents/elephant_agent.py
   Increment stats_version by 1 from whatever it currently is.
4. git add the changed weights files and agent files
5. Commit with message: "Deploy latest training weights + reset stats"
6. git push
7. Report what was updated, the new stats_versions, and the new win rates from the training logs.

Notes:
- Do NOT read ian1_agent.py or ian2_agent.py
- If a weights file is identical to what's already committed (git diff shows nothing), skip it — no point bumping stats for no change
- Elephant weights may not exist yet if training hasn't found a best — that's fine, just skip it
- training/*/best_policy.json and checkpoint.json are gitignored — never commit them, only agents/*_weights.json
