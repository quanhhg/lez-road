[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.843102,105.530536,20.888438,105.578770)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.843102,105.530536,20.888438,105.578770);
  node["barrier"](20.843102,105.530536,20.888438,105.578770);
);
(._; >>;);
out meta;
out count;
