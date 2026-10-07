[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.707027,105.674106,20.752401,105.722337)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.707027,105.674106,20.752401,105.722337);
  node["barrier"](20.707027,105.674106,20.752401,105.722337);
);
(._; >>;);
out meta;
out count;
