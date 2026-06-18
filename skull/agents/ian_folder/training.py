import time
import random
from concurrent.futures import ProcessPoolExecutor, as_completed, Future

from skull.agents.base import SkullAgent
from skull.agents.ian1 import Ian1, Genes
from skull.agents.random_agent import RandomSkullAgent
from skull.engine import SkullEngine

PLAYERS_COUNT = 4
SIMULATIONS_TO_RUN_AGAINST_ONE_AGENT = 1000
SIMULATIONS_TO_RUN = 1_000_000
POPULATION_SIZE = 1024
GENERATION_SAMPLE_SIZE = 32
PARAMETER_SIZE = 19
NUMBER_OF_GENERATIONS = 100

class WinRate:
    def __init__(self):
        self.games = 0
        self.wins = 0

    def win(self):
        self.games += 1
        self.wins += 1

    def loss(self):
        self.games += 1

    def get_win_rate(self):
        if self.games == 0:
            return 0
        return self.wins / self.games * 100

class Simulator:
    def __init__(self):
        self.rng = random.Random(42)
    def main(self):
        agents = self.get_initial_agents()
        for generation in range(NUMBER_OF_GENERATIONS):
            print(f"-------GENERATION {generation}-------")
            fitness_map = self.get_generation_fitness(agents)
            sorted_fitness_map: list[tuple[Ian1, float]] = sorted(fitness_map.items(),
                                                                  key= lambda item: item[1], reverse=True)
            sampled_agents = sorted_fitness_map[:GENERATION_SAMPLE_SIZE]
            self.print_agents_with_fitness(sampled_agents)
            agents = self.create_next_generation(sampled_agents)

    def get_initial_agents(self) -> list[Ian1]:
        agents = []
        for i in range(POPULATION_SIZE):
            params = []
            for _ in range(PARAMETER_SIZE):
                param = self.rng.randint(0, 100)
                params.append(param)
            print(f"params = {params}")
            gene: Genes = Genes(params, random.Random()).normalize()
            print(f"gene = {gene}")
            agents.append(Ian1(secret_meta_value1=gene))

        return agents

    def get_generation_fitness(self, agents: list[Ian1]) -> dict[Ian1, float]:
        start_time = time.perf_counter()
        fitness_map = {}
        completed_tasks = 0
        futures: list[Future] = []
        win_rate: dict[SkullAgent, WinRate] = {}
        for agent in agents:
            win_rate[agent] = WinRate()
        with ProcessPoolExecutor() as executor:
            for simulations in range(SIMULATIONS_TO_RUN):
                sampled_agents = self.rng.sample(agents, k=PLAYERS_COUNT)
                futures.append(executor.submit(self.simulate_game, sampled_agents))
            sum = 0
            max_fitness = 0
            best_agent = None

            for future in as_completed(futures):
                completed_tasks += 1
                percent_complete = completed_tasks / len(futures) * 100
                print(f"\rProgress: {percent_complete:.1f}% ({completed_tasks}/{len(futures)} completed)", end="")
                result = future.result()
                for agent, did_win in result:
                    if did_win:
                        
                    win_rate[agent]
                fitness_map[agent] = fitness
                sum += fitness
                if fitness > max_fitness:
                    max_fitness = fitness
                    best_agent = agent
            print(f"\nAverage fitness = {sum / POPULATION_SIZE}")
            print(f"Max fitness = {max_fitness}")
            print(f"Best agent = {best_agent.gene}")
            print(f"Total time = {time.perf_counter() - start_time} seconds")
            return fitness_map

    def simulate_game(self, agents: list[SkullAgent]) -> dict[SkullAgent, bool]:
        """
        Simulates the game and returns the winner in a map
        """
        engine = SkullEngine(agents)
        result = engine.play_game(PLAYERS_COUNT)
        winner = result.get("winner")
        winner_map: dict[SkullAgent, bool] = {}
        for index, agent in enumerate(agents):
            if winner == index:
                winner_map[agent] = True
            else:
                winner_map[agent] = False
        return winner_map

    def get_generation_fitness_against_one_agent(self, agents: list[Ian1], base_line_agent_type: type[SkullAgent] = RandomSkullAgent) -> dict[Ian1, float]:
        start_time = time.perf_counter()
        fitness_map = {}
        completed_tasks = 0
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self.get_fitness_against_one_agent, agent, base_line_agent_type): agent for agent in agents}
            sum = 0
            max_fitness = 0
            best_agent = None

            for future in as_completed(futures):
                completed_tasks += 1
                percent_complete = completed_tasks / len(agents) * 100
                print(f"\rProgress: {percent_complete:.1f}% ({completed_tasks}/{len(agents)} completed)", end="")
                agent = futures[future]
                fitness = future.result()
                fitness_map[agent] = fitness
                sum += fitness
                if fitness > max_fitness:
                    max_fitness = fitness
                    best_agent = agent
            print(f"\nAverage fitness = {sum / POPULATION_SIZE}")
            print(f"Max fitness = {max_fitness}")
            print(f"Best agent = {best_agent.gene}")
            print(f"Total time = {time.perf_counter() - start_time} seconds")
            return fitness_map

    def get_fitness_against_one_agent(self, agent: Ian1, base_line_agent_type: type[SkullAgent]) -> float:
        agents = [agent, base_line_agent_type(), base_line_agent_type(), base_line_agent_type()]
        engine = SkullEngine(agents)

        wins = 0
        for cycle in range(SIMULATIONS_TO_RUN_AGAINST_ONE_AGENT):
            result = engine.play_game(PLAYERS_COUNT)
            if result.get("winner") == 0:
                wins += 1
        fitness = wins / SIMULATIONS_TO_RUN_AGAINST_ONE_AGENT * 100
        return fitness


    def print_agents_with_fitness(self, agents: list[tuple[Ian1, float]]):
        print(f"Sampled agents:")
        for agent, fitness in agents:
            print(f"   Win rate: {fitness}%, gene: {agent.gene}")

    def create_next_generation(self, agents: list[tuple[Ian1, float]]) -> list[Ian1]:
        next_generation = []
        for mom, _ in agents:
            for dad, _ in agents:
                next_generation.append(mom.breed(dad).mutate().normalize())
        return next_generation

if __name__ == "__main__":
    Simulator().main()
