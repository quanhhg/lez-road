[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.067992,105.771978,21.113395,105.820356)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.067992,105.771978,21.113395,105.820356);
  node["barrier"](21.067992,105.771978,21.113395,105.820356);
);
(._; >>;);
out meta;
out count;
