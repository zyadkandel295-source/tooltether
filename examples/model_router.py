from tooltether import ModelCandidate, select_model

if __name__ == "__main__":
    candidates = [
        ModelCandidate(
            provider="local", model="fast", estimated_cost=0, estimated_latency=1, quality=0.7
        ),
        ModelCandidate(
            provider="remote", model="quality", estimated_cost=3, estimated_latency=2, quality=0.95
        ),
    ]
    print(select_model(candidates, objective="balanced").explanation)
