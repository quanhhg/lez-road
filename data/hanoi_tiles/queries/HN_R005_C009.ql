[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.752203,105.674306,20.797578,105.722552)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.752203,105.674306,20.797578,105.722552);
  node["barrier"](20.752203,105.674306,20.797578,105.722552);
);
(._; >>;);
out meta;
out count;
