[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.113166,105.772211,21.158569,105.820605)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.113166,105.772211,21.158569,105.820605);
  node["barrier"](21.113166,105.772211,21.158569,105.820605);
);
(._; >>;);
out meta;
out count;
