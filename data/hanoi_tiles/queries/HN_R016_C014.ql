[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.247918,105.917470,21.293362,105.965952)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.247918,105.917470,21.293362,105.965952);
  node["barrier"](21.247918,105.917470,21.293362,105.965952);
);
(._; >>;);
out meta;
out count;
