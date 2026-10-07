[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.616246,105.769677,20.661646,105.817906)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.616246,105.769677,20.661646,105.817906);
  node["barrier"](20.616246,105.769677,20.661646,105.817906);
);
(._; >>;);
out meta;
out count;
