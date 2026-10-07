[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.797170,105.722549,20.842558,105.770823)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.797170,105.722549,20.842558,105.770823);
  node["barrier"](20.797170,105.722549,20.842558,105.770823);
);
(._; >>;);
out meta;
out count;
