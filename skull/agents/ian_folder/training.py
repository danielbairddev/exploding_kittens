import time
import random
from concurrent.futures import ProcessPoolExecutor

from skull.agents.ian1 import Ian1, Genes
from skull.agents.random_agent import RandomSkullAgent
from skull.engine import SkullEngine

PLAYERS_COUNT = 4
SIMULATIONS_TO_RUN = 1000
POPULATION_SIZE = 1000
PARAMETER_SIZE = 19

class Simulator:
    def __init__(self):
        self.rng = random.Random(42)
    def main(self):
        agents = self.get_initial_agents()
        start_time = time.perf_counter()
        fitness_map = {}
        with ProcessPoolExecutor() as executor:
            results = executor.map(self.get_fitness, agents)
            sum = 0
            max_fitness = 0
            best_agent = None
            for agent, fitness in zip(agents, results):
                fitness_map[agent] = fitness
                sum += fitness
                if fitness > max_fitness:
                    max_fitness = fitness
                    best_agent = agent
            print(f"Average fitness = {sum / POPULATION_SIZE}")
            print(f"Max max_fitness = {max_fitness}")
            print(f"Best agent = {best_agent.gene}")
            print(f"Total time = {time.perf_counter() - start_time} seconds")

    def get_initial_agents(self) -> list[Ian1]:
        agents = []
        for i in range(POPULATION_SIZE):
            params = []
            for _ in range(PARAMETER_SIZE):
                param = self.rng.randint(0, 100)
                params.append(param)
            print(f"params = {params}")
            gene: Genes = Genes(params, self.rng).normalize()
            print(f"gene = {gene}")
            agents.append(Ian1(gene=gene))

        return agents

    def get_fitness(self, agent: Ian1):
        start_time = time.perf_counter()
        agents = [agent, RandomSkullAgent(), RandomSkullAgent(), RandomSkullAgent()]
        engine = SkullEngine(agents)

        wins = 0
        for cycle in range(SIMULATIONS_TO_RUN):
            result = engine.play_game(PLAYERS_COUNT)
            if result.get("winner") == 0:
                wins += 1
        fitness = wins / SIMULATIONS_TO_RUN * 100
        print(f"Agent wins {fitness}% of the time. Calculated in {time.perf_counter() - start_time} seconds")
        return fitness

if __name__ == "__main__":
    Simulator().main()
