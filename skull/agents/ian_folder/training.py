import time
import random
from concurrent.futures import ProcessPoolExecutor

from skull.agents.ian1 import Ian1, Genes
from skull.agents.random_agent import RandomSkullAgent
from skull.engine import SkullEngine

PLAYERS_COUNT = 4
SIMULATIONS_TO_RUN = 1000
POPULATION_SIZE = 1024
GENERATION_SAMPLE_SIZE = 32
PARAMETER_SIZE = 19
NUMBER_OF_GENERATIONS = 100

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
            sampled_agents = sorted_fitness_map[:NUMBER_OF_GENERATIONS]
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
            gene: Genes = Genes(params, self.rng).normalize()
            print(f"gene = {gene}")
            agents.append(Ian1(secret_meta_value1=gene))

        return agents


    def get_generation_fitness(self, agents: list[Ian1]) -> dict[Ian1, float]:
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
            print(f"Max fitness = {max_fitness}")
            print(f"Best agent = {best_agent.gene}")
            print(f"Total time = {time.perf_counter() - start_time} seconds")
            return fitness_map

    def get_fitness(self, agent: Ian1) -> float:
        agents = [agent, RandomSkullAgent(), RandomSkullAgent(), RandomSkullAgent()]
        engine = SkullEngine(agents)

        wins = 0
        for cycle in range(SIMULATIONS_TO_RUN):
            result = engine.play_game(PLAYERS_COUNT)
            if result.get("winner") == 0:
                wins += 1
        fitness = wins / SIMULATIONS_TO_RUN * 100
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
