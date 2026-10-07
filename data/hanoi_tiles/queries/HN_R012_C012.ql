[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.067753,105.820105,21.113169,105.868497)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.067753,105.820105,21.113169,105.868497);
  node["barrier"](21.067753,105.820105,21.113169,105.868497);
);
(._; >>;);
out meta;
out count;
