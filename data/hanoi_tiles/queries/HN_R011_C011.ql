[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.022819,105.771745,21.068221,105.820108)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.022819,105.771745,21.068221,105.820108);
  node["barrier"](21.022819,105.771745,21.068221,105.820108);
);
(._; >>;);
out meta;
out count;
