### **Hades-v2: Exploding Kittens Anti-Agent Architecture & Reference**

**Goal:** Train an agent to intentionally lose (die) against a fleet of 4 other loser bots. 
**Core Update:** Transition from GRU to a Transformer encoder for exact memory retention, upgrade heads for continuous placement, and implement dense auxiliary reward shaping while maintaining a strict binary win/loss terminal reward.

#### **1. State Representation Enhancements (Inputs)**

* **1.1. Event Sequence (The Event Transformer):**
    * **Vector ($E_t$):** 64 dimensions per event.
    * **Components:** `event_type` (14) | `actor_rel_seat` (5) | `target_rel_seat` (6) | `card_played` (14) | `card_given` (14) | `turn_number_norm` (1) | `is_my_turn` (1) | `action_resolved` (1) | `cards_to_draw` (1) | `padding_mask` (1) | `reserved` (6)
    * **Context Window:** Last $N=128$ events.
* **1.2. Snapshot Vector ($S_t$):**
    * Expanded to 134 dimensions.
    * **Core Counts (42 dims):** `hand_counts` (14) | `discard_counts` (14) | `unseen_frac` (14)
    * **Scalars (10 dims):** `deck_size_norm` | `cards_to_draw` | `n_alive` | `my_hand_size` | `my_defuses` | `ek_draw_prob` | `known_eks_in_deck` | `turns_to_my_turn` | `nopes_in_wild` | `defuses_in_wild`
    * **Opponent Matrix Flattened (40 dims):** For each of the 4 opponents (10 dims each): `hand_size` | `known_defuses_used` | `prob_has_defuse` | `is_alive` | `times_attacked_me` | `defuses_given_to_me` | `cards_stolen_from_me` | `play_rate` | `nope_rate` | `is_targeted_often`
    * **Exact Deck State (42 dims):** A spatial representation of the top of the deck based on STF. 14 card types $\times$ top 3 positions (flattened). If a position is unknown, all zeros.

#### **2. Core Architecture Redesign**

* **2.1. Memory Module (Transformer Encoder):**
    * **Input:** $128 \times 64$ event sequence.
    * Apply Absolute Positional Encoding to the sequence.
    * **Architecture:** 3 Layers, 4 Attention Heads, Hidden Dimension = 128, Feedforward Dimension = 256, Dropout = 0.1.
    * **Pooling:** Concatenate the Global Average Pooling of the sequence with the Last Token Output.
    * **Output:** $H_{\text{mem}} \in \mathbb{R}^{256}$.
* **2.2. The Trunk:**
    * Concatenate Transformer Output ($H_{\text{mem}}$) with Snapshot ($S_t$).
    * **Input size:** $256 + 134 = 390$.
    * Linear(390 $\rightarrow$ 256) $\rightarrow$ LayerNorm $\rightarrow$ Mish
    * Linear(256 $\rightarrow$ 128) $\rightarrow$ LayerNorm $\rightarrow$ Mish
    * **Output:** $A_{\text{core}} \in \mathbb{R}^{128}$.

#### **3. Head Routing & Specification**

* **3.1. Policy Head (Action Selection):**
    * Linear(128 $\rightarrow$ 8 logits). Apply action mask ($-10^9$ to illegal logits) before Softmax.
* **3.2. Value Head (Critic):**
    * Linear(128 $\rightarrow$ 1). Unactivated.
* **3.3. Target Head (Opponent Selection):**
    * Linear(128 $\rightarrow$ 5 logits). (0-3 are relative seats, 4 is 'None/Self'). Mask dead players.
* **3.4. Nope Head (Context-Aware):**
    * **Input Context ($C_{\text{nope}}$):** `action_type_being_played` (8) + `card_being_played` (14) + `targets_me` (1) + `already_noped_count` (1).
    * Concatenate $A_{\text{core}}$ and $C_{\text{nope}}$ (128 + 24 = 152).
    * Linear(152 $\rightarrow$ 64) $\rightarrow$ Mish $\rightarrow$ Linear(64 $\rightarrow$ 1). Output is Sigmoid probability.
* **3.5. Give Head (Anti-Theft):**
    * Linear(128 $\rightarrow$ 14 logits). Mask cards not currently in hand.
    * *Intent:* Network must learn to hand over Defuses/Nopes when Favored or Cat-Stolen.
* **3.6. Place Head (Suicide Deck Placement):**
    * Linear(128 $\rightarrow$ 50 logits) (Assuming max deck size is < 50).
    * Mask all indices $\ge$ `current_deck_size` with $-10^9$. Output is Softmax distribution over exact deck depths.
    * *Intent:* The bot must learn to place the EK exactly at the index matching `turns_to_my_turn` to ensure self-destruction.

#### **4. Reward Shaping & Loss Formulation**

* **4.1. Terminal Reward ($R_{\text{term}}$):**
    * Finish position (1st, 2nd, etc.) is entirely irrelevant.
    * If the bot dies at any point = $+1.0$ (Loss / Success).
    * If the bot is the final survivor = $-1.0$ (Win / Failure).
* **4.2. Dense Auxiliary Rewards ($R_{\text{aux}}$):**
    * $r_{\text{give\_defuse}} = +0.2$ (Triggered when willingly giving a Defuse via Favor/Cat).
    * $r_{\text{waste\_defuse}} = +0.2$ (Triggered when successfully defusing an EK to keep the game going/drain resources).
    * $r_{\text{draw\_safe}} = -0.05$ (Penalizes drawing a non-EK card to discourage extending lifespan).
    * **Total Step Reward:** $R_t = R_{\text{term}} + \sum R_{\text{aux}}$.
* **4.3. PPO Loss Objectives:**
    * Standard Clipped Surrogate Objective ($\epsilon = 0.2$).
    * Value Loss: Huber Loss between Critic output and Discounted Returns ($\gamma = 0.99$).
    * Entropy Bonus: High coefficient initially ($c_2 = 0.05$), decaying to $0.01$ to force exploration of suicide permutations early on.

#### **5. Training Curriculum & Evaluator**

* **Phase 1: Bootstrapping Anti-Logic (0 - 5M Steps):** Opponents are 100% standard winner bots (Rhino/Elephant) to force the policy into rapid self-destruction via hoarding and drawing.
* **Phase 2: The Loser Crucible (5M - 20M Steps):** Opponents are 80% Loser Fleet (Ian 1-3, Perdition, Gabriel), 20% Self-Play (sampling from last 5 checkpoints).
* **Evaluation Metric for Success:** Run 10,000 matches against [Ian3, Ian3, Perdition2, Gabriel]. Target is a survival rate of $< 2\%$ for Hades-v2.

***

### **Implementation Reference / Glossary**

#### **Event Sequence Variables ($E_t$)**
* **`event_type`**: 14-dim one-hot. Categorizes the event (e.g., Draw, Play Card, Nope, Defuse, Die, Give Card, etc.).
* **`actor_rel_seat`**: 5-dim one-hot. The relative seat of the player initiating the event (0 = self, 1 = next player, etc.).
* **`target_rel_seat`**: 6-dim one-hot. The relative seat of the player receiving the action (0-4). The 6th index is `None` (for actions like Shuffle or Draw).
* **`card_played` & `card_given`**: 14-dim one-hots matching the 14 card types in the game deck.
* **`turn_number_norm`**: Scalar. `current_turn / 100`. Helps the Transformer ground how deep into the game the event occurred.
* **`action_resolved`**: Boolean (1/0). True if a played card actually took effect (was not Noped). Critical for the Transformer to track actual deck/hand changes.
* **`cards_to_draw`**: Scalar. The size of the attack stack / mandatory draws at the exact moment the event occurred.

#### **Snapshot Variables ($S_t$)**
* **`unseen_frac`**: 14-dim vector. For each card type, `(Total_in_Game - Hand_Count - Discard_Count) / Total_in_Game`. Represents the probability mass of cards remaining in the deck and opponent hands.
* **`deck_size_norm`**: Scalar. `current_deck_size / starting_deck_size`.
* **`known_eks_in_deck`**: Scalar. Explicit count of Exploding Kittens currently in the draw pile (Total players - 1 - Dead players). 
* **`turns_to_my_turn`**: Scalar. Number of player turns before the bot acts again (accounts for skips/attacks currently resolving).
* **`nopes_in_wild` & `defuses_in_wild`**: Scalars. Calculated by `Total_in_Game - In_My_Hand - In_Discard_Pile`. Critical for predicting if a suicide attempt can be countered.
* **`prob_has_defuse` (Opponent)**: Scalar (0.0 - 1.0). Tracked by monitoring an opponent's draw history. If an opponent draws a card and doesn't explode, probability updates based on unseen fractions. If they draw from an STF, updates based on exact known cards.
* **`defuses_given_to_me` (Opponent)**: Scalar. Count of times this specific opponent has given the bot a Defuse. Detects other "loser" bots.
* **`play_rate` (Opponent)**: Scalar. Rolling average of cards played per turn. High rate = winner bot trying to survive. Low rate = loser bot hoarding cards.
* **`nope_rate` (Opponent)**: Scalar. Probability this opponent will Nope an action when they are known/suspected to have a Nope. 
* **`Exact Deck State`**: 42-dim flattened tensor. Built from See The Future (STF) data. e.g., If the bot knows the top card is a Defuse, the first 14 dimensions will have a `1` at the Defuse index. If the second card is unknown, the next 14 dimensions are all `0`.
