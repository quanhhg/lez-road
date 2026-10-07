[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.024239,105.386824,21.069535,105.435075)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.024239,105.386824,21.069535,105.435075);
  node["barrier"](21.024239,105.386824,21.069535,105.435075);
);
(._; >>;);
out meta;
out count;
